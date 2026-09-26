from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.decision import LexicalSimilarity, SimilarityBackend, clamp
from backend.media import parse_sidecar_subtitles
from backend.schemas import ModelReport, SpeechSegment


@dataclass(frozen=True)
class SceneContext:
    dominant_activity: str
    activities: list[str]
    contexts: list[str]
    mood: str
    description: str


CONTEXT_TERMS: dict[str, tuple[str, ...]] = {
    "funeral": ("funeral", "mourning", "death", "শোক", "মৃত্যু", "অন্ত্যেষ্টি"),
    "medical emergency": (
        "hospital",
        "doctor",
        "injury",
        "blood",
        "হাসপাতাল",
        "ডাক্তার",
        "আহত",
        "রক্ত",
    ),
    "violence": ("fight", "weapon", "murder", "attack", "মারামারি", "হত্যা", "বন্দুক"),
    "cooking": ("cook", "kitchen", "meal", "food", "রান্না", "খাবার", "রান্নাঘর"),
    "travel": ("travel", "train", "road", "journey", "ভ্রমণ", "ট্রেন", "রাস্তা"),
    "family": ("family", "homecoming", "পরিবার", "বাড়ি"),
    "celebration": ("celebrate", "festival", "birthday", "উৎসব", "জন্মদিন", "উদযাপন"),
    "study": ("study", "school", "book", "পড়াশোনা", "স্কুল", "বই"),
    "work": ("work", "office", "meeting", "অফিস", "কাজ"),
    "romance": ("romance", "love", "wedding", "প্রেম", "বিয়ে"),
    "stargazing": ("stargazing", "night sky", "stars", "তারাভরা", "আকাশ"),
}


def _fallback_context(transcript: str) -> SceneContext:
    text = transcript.casefold()
    contexts = [
        context
        for context, terms in CONTEXT_TERMS.items()
        if any(term in text for term in terms)
    ]
    safety_priority = ["funeral", "medical emergency", "violence"]
    activity_priority = [
        "cooking",
        "travel",
        "stargazing",
        "study",
        "work",
        "celebration",
        "romance",
        "family",
    ]
    dominant_activity = next(
        (value for value in activity_priority if value in contexts),
        "conversation" if transcript.strip() else "quiet scene",
    )
    if any(context in contexts for context in safety_priority):
        mood = "somber" if "funeral" in contexts else "tense"
    elif "celebration" in contexts:
        mood = "joyful"
    else:
        mood = "calm"
    description = (
        transcript.strip() or "A visually detected scene without reliable dialogue."
    )
    return SceneContext(
        dominant_activity=dominant_activity,
        activities=[dominant_activity],
        contexts=contexts or (["dialogue"] if transcript.strip() else ["visual scene"]),
        mood=mood,
        description=description[:500],
    )


class AdaptiveSimilarity(SimilarityBackend):
    def __init__(self, settings: Settings, note_failure: Any) -> None:
        self.settings = settings
        self.note_failure = note_failure
        self.fallback = LexicalSimilarity()
        self.encoder: Any = None
        self.failed = False
        self.cache: dict[str, Any] = {}
        self.lock = threading.Lock()

    @property
    def name(self) -> str:
        return (
            self.settings.semantic_model_id
            if self.encoder is not None
            else self.fallback.name
        )

    def _ensure_encoder(self) -> Any:
        if (
            self.encoder is not None
            or self.failed
            or not self.settings.enable_semantic_model
        ):
            return self.encoder
        with self.lock:
            if self.encoder is not None or self.failed:
                return self.encoder
            try:
                from sentence_transformers import SentenceTransformer

                self.encoder = SentenceTransformer(
                    self.settings.semantic_model_id,
                    device="cpu",
                )
            except Exception as error:
                self.failed = True
                self.note_failure(f"Semantic model unavailable: {type(error).__name__}")
        return self.encoder

    def _encode(self, value: str) -> Any:
        normalised = value.strip().casefold()
        if normalised not in self.cache:
            self.cache[normalised] = self.encoder.encode(
                normalised,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return self.cache[normalised]

    def similarity(self, left: str, right: str) -> float:
        if not left.strip() or not right.strip():
            return 0.0
        if self._ensure_encoder() is None:
            return self.fallback.similarity(left, right)
        try:
            left_vector = self._encode(left)
            right_vector = self._encode(right)
            return clamp(float(left_vector @ right_vector))
        except Exception as error:
            self.failed = True
            self.note_failure(f"Semantic inference failed: {type(error).__name__}")
            return self.fallback.similarity(left, right)


class ModelRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.notes: list[str] = []
        self._asr_model: Any = None
        self._vlm_model: Any = None
        self._vlm_processor: Any = None
        self._vlm_failed = False
        self._lock = threading.Lock()
        self.similarity = AdaptiveSimilarity(settings, self._note)

    def _note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)

    def transcribe(self, video_path: Path) -> list[SpeechSegment]:
        sidecar_segments = parse_sidecar_subtitles(video_path)
        if sidecar_segments:
            return sidecar_segments
        if not self.settings.enable_asr:
            self._note("ASR disabled; silence gating remains active")
            return []
        try:
            with self._lock:
                if self._asr_model is None:
                    from faster_whisper import WhisperModel

                    self._asr_model = WhisperModel(
                        self.settings.asr_model_id,
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=self.settings.model_cpu_threads,
                    )
            segments, _ = self._asr_model.transcribe(
                str(video_path),
                language="bn",
                beam_size=1,
                vad_filter=True,
                word_timestamps=True,
            )
            return [
                SpeechSegment(
                    start=segment.start, end=segment.end, text=segment.text.strip()
                )
                for segment in segments
                if segment.end > segment.start
            ]
        except Exception as error:
            self._note(f"ASR unavailable: {type(error).__name__}; silence gating used")
            return []

    def describe_scene(self, frame_path: Path | None, transcript: str) -> SceneContext:
        fallback = _fallback_context(transcript)
        if not self.settings.enable_vlm or frame_path is None or self._vlm_failed:
            self._note("VLM disabled; transcript context fallback used")
            return fallback
        try:
            self._ensure_vlm()
            from PIL import Image

            image = Image.open(frame_path).convert("RGB")
            prompt = (
                "Analyse this Bengali drama frame with its nearby transcript. "
                "Return only compact JSON with keys dominant_activity, activities, "
                "contexts, mood, description. Contexts must explicitly include "
                "safety-sensitive concepts such as funeral, grief, medical emergency, "
                "injury, violence, alcohol, children, cooking, eating, travel, "
                "celebration when visible or stated. "
                f"Transcript: {transcript[:1200]}"
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            inputs = self._vlm_processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to("cpu")
            generated = self._vlm_model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=120,
            )
            prompt_length = inputs["input_ids"].shape[1]
            text = self._vlm_processor.batch_decode(
                generated[:, prompt_length:], skip_special_tokens=True
            )[0]
            payload = self._extract_json(text)
            return SceneContext(
                dominant_activity=str(payload["dominant_activity"]).strip().lower(),
                activities=self._string_list(payload.get("activities")),
                contexts=self._string_list(payload.get("contexts")),
                mood=str(payload.get("mood", fallback.mood)).strip().lower(),
                description=str(
                    payload.get("description", fallback.description)
                ).strip()[:500],
            )
        except Exception as error:
            self._vlm_failed = True
            self._note(
                f"VLM unavailable: {type(error).__name__}; transcript fallback used"
            )
            return fallback

    def _ensure_vlm(self) -> None:
        if self._vlm_model is not None:
            return
        with self._lock:
            if self._vlm_model is not None:
                return
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor

            torch.set_num_threads(self.settings.model_cpu_threads)
            self._vlm_processor = AutoProcessor.from_pretrained(
                self.settings.vlm_model_id
            )
            self._vlm_model = AutoModelForImageTextToText.from_pretrained(
                self.settings.vlm_model_id,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
            ).to("cpu")
            self._vlm_model.eval()

    @staticmethod
    def _extract_json(value: str) -> dict[str, Any]:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("VLM did not return JSON")
        result = json.loads(value[start : end + 1])
        if not isinstance(result, dict) or not result.get("dominant_activity"):
            raise ValueError("VLM JSON is missing dominant_activity")
        return result

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip().lower() for item in value if str(item).strip()][:12]

    def report(self, used_sidecar: bool = False) -> ModelReport:
        speech_name = (
            "timed subtitle track"
            if used_sidecar
            else self.settings.asr_model_id
            if self._asr_model is not None
            else "audio silence fallback"
        )
        visual_name = (
            self.settings.vlm_model_id
            if self._vlm_model is not None
            else "FFmpeg + transcript fallback"
        )
        degraded = bool(self.notes)
        return ModelReport(
            visual=visual_name,
            speech=speech_name,
            semantics=self.similarity.name,
            degraded=degraded,
            notes=list(self.notes),
        )
