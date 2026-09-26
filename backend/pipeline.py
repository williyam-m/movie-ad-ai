from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from backend.config import Settings
from backend.decision import clamp, match_brand, score_boundary, select_paced_candidates
from backend.media import (
    MediaProcessingError,
    SceneCut,
    assert_media_tools,
    detect_scene_cuts,
    detect_silences,
    extract_frame,
    load_timed_scene_contexts,
    normalise_scene_change,
    probe_duration,
    silence_near,
)
from backend.model_runtime import ModelRuntime, SceneContext
from backend.schemas import (
    AnalysisResult,
    AnalysisSummary,
    BoundaryObservation,
    Brand,
    BrandSummary,
    BreakSlot,
    PacingPolicy,
    Scene,
    SpeechSegment,
)
from backend.vmap import build_vmap, format_time_offset

ProgressCallback = Callable[[str, float], None]


def _transcript_for_scene(
    segments: list[SpeechSegment], start: float, end: float
) -> str:
    return " ".join(
        segment.text
        for segment in segments
        if segment.end > start and segment.start < end and segment.text
    ).strip()


def _scene_for_timestamp(scenes: list[Scene], timestamp: float) -> tuple[Scene, Scene]:
    for index in range(len(scenes) - 1):
        if abs(scenes[index].end - timestamp) <= 0.25:
            return scenes[index], scenes[index + 1]
    preceding = max(
        (scene for scene in scenes if scene.start < timestamp),
        key=lambda scene: scene.start,
    )
    following = min(
        (scene for scene in scenes if scene.end > timestamp),
        key=lambda scene: scene.end,
    )
    return preceding, following


class VideoAnalysisPipeline:
    def __init__(self, settings: Settings, models: ModelRuntime | None = None) -> None:
        self.settings = settings
        self.models = models or ModelRuntime(settings)

    def analyse(
        self,
        job_id: str,
        source_path: Path,
        source_name: str,
        media_url: str,
        brands: list[Brand],
        policy: PacingPolicy,
        job_dir: Path,
        progress: ProgressCallback | None = None,
    ) -> AnalysisResult:
        update = progress or (lambda _stage, _progress: None)
        assert_media_tools(self.settings)
        job_dir.mkdir(parents=True, exist_ok=True)

        update("Reading programme metadata", 0.05)
        duration = probe_duration(source_path, self.settings)
        if duration < 20:
            raise MediaProcessingError("Video must be at least 20 seconds long")

        update("Detecting visual scene changes", 0.14)
        cuts = [
            cut
            for cut in detect_scene_cuts(source_path, self.settings)
            if 0.5 < cut.timestamp < duration - 0.5
        ]

        update("Measuring dialogue-safe silence", 0.26)
        silences = detect_silences(source_path, duration, self.settings)
        speech_segments = self.models.transcribe(source_path)
        used_sidecar = source_path.with_suffix(".srt").is_file() and bool(
            speech_segments
        )
        used_scene_context = source_path.with_suffix(".scenes.json").is_file()

        update("Building semantic scenes", 0.40)
        scenes = self._build_scenes(
            source_path,
            duration,
            cuts,
            speech_segments,
            job_dir / "frames",
            update,
        )

        update("Scoring interruption safety", 0.72)
        candidates = []
        brand_matches = {}
        for index, cut in enumerate(cuts):
            scene_before, scene_after = _scene_for_timestamp(scenes, cut.timestamp)
            visual_change = normalise_scene_change(
                cut.score, self.settings.scene_threshold
            )
            semantic_similarity = self.models.similarity.similarity(
                f"{scene_before.dominant_activity} {scene_before.description}",
                f"{scene_after.dominant_activity} {scene_after.description}",
            )
            candidate = score_boundary(
                BoundaryObservation(
                    timestamp=cut.timestamp,
                    visual_change=visual_change,
                    silence_seconds=silence_near(cut.timestamp, silences),
                    semantic_shift=clamp(1 - semantic_similarity),
                ),
                speech_segments,
                duration,
                policy,
            )
            candidates.append(candidate)
            if candidate.is_safe:
                brand_matches[candidate.id] = match_brand(
                    scene_before,
                    scene_after,
                    brands,
                    self.models.similarity,
                )
            update(
                "Scoring interruption safety",
                0.72 + 0.08 * ((index + 1) / max(len(cuts), 1)),
            )

        matchable_candidates = [
            candidate
            for candidate in candidates
            if candidate.is_safe and brand_matches.get(candidate.id) is not None
        ]
        conservative_ad_duration = max(
            (
                brand_matches[candidate.id].brand.duration_seconds
                for candidate in matchable_candidates
            ),
            default=6.0,
        )
        scheduled = select_paced_candidates(
            matchable_candidates,
            duration,
            policy,
            conservative_ad_duration,
        )

        update("Matching context-safe creatives", 0.84)
        breaks: list[BreakSlot] = []
        for index, candidate in enumerate(scheduled, start=1):
            scene_before, scene_after = _scene_for_timestamp(
                scenes, candidate.timestamp
            )
            match = brand_matches[candidate.id]
            brand = match.brand
            breaks.append(
                BreakSlot(
                    id=f"break-{index:02}",
                    timestamp=candidate.timestamp,
                    time_offset=format_time_offset(candidate.timestamp),
                    score=candidate.interruptibility_score,
                    scene_id=scene_after.id,
                    brand=BrandSummary(
                        id=brand.id,
                        name=brand.name,
                        category=brand.category,
                        tagline=brand.tagline,
                        color=brand.color,
                    ),
                    creative_url=brand.creative_path,
                    duration=brand.duration_seconds,
                    match_score=match.score,
                    why=[
                        *match.reasons,
                        f"safe transition from {scene_before.id} to {scene_after.id}",
                    ],
                    blocked_brands=match.blocked_brand_ids,
                )
            )

        total_ad_seconds = sum(slot.duration for slot in breaks)
        ad_load_percent = (
            total_ad_seconds / (duration + total_ad_seconds) * 100
            if total_ad_seconds
            else 0.0
        )
        manifest_url = f"/api/jobs/{job_id}/manifest.vmap"
        debug_url = f"/api/jobs/{job_id}/debug.json"
        result = AnalysisResult(
            job_id=job_id,
            source_name=source_name,
            duration_seconds=round(duration, 3),
            media_url=media_url,
            generated_at=datetime.now(UTC),
            summary=AnalysisSummary(
                scene_count=len(scenes),
                candidate_count=len(candidates),
                safe_candidate_count=sum(candidate.is_safe for candidate in candidates),
                break_count=len(breaks),
                ad_load_percent=round(ad_load_percent, 3),
            ),
            policy=policy,
            models=self.models.report(used_sidecar, used_scene_context),
            scenes=scenes,
            candidates=candidates,
            breaks=breaks,
            manifest_url=manifest_url,
            debug_url=debug_url,
        )

        update("Writing VMAP and debug artefacts", 0.94)
        (job_dir / "manifest.vmap").write_text(
            build_vmap(job_id, breaks, self.settings.public_base_url),
            encoding="utf-8",
        )
        (job_dir / "debug.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        update("Analysis complete", 1.0)
        return result

    def _build_scenes(
        self,
        source_path: Path,
        duration: float,
        cuts: list[SceneCut],
        speech_segments: list[SpeechSegment],
        frame_dir: Path,
        progress: ProgressCallback,
    ) -> list[Scene]:
        boundaries = [0.0, *[cut.timestamp for cut in cuts], duration]
        timed_contexts = load_timed_scene_contexts(source_path)
        scenes: list[Scene] = []
        for index, (start, end) in enumerate(
            zip(boundaries, boundaries[1:], strict=False)
        ):
            midpoint = start + (end - start) / 2
            transcript = _transcript_for_scene(speech_segments, start, end)
            timed_context = next(
                (
                    context
                    for context in timed_contexts
                    if context.start <= midpoint < context.end
                ),
                None,
            )
            fallback_context = (
                SceneContext(
                    dominant_activity=timed_context.dominant_activity,
                    activities=timed_context.activities,
                    contexts=timed_context.contexts,
                    mood=timed_context.mood,
                    description=timed_context.description,
                )
                if timed_context
                else None
            )
            frame_path: Path | None = None
            if index < self.settings.max_vlm_scenes and self.models.needs_visual_frame:
                candidate_frame = frame_dir / f"scene-{index + 1:04}.jpg"
                try:
                    frame_path = extract_frame(
                        source_path, midpoint, candidate_frame, self.settings
                    )
                except MediaProcessingError:
                    frame_path = None
            context = self.models.describe_scene(
                frame_path, transcript, fallback_context
            )
            start_visual_score = (
                normalise_scene_change(
                    cuts[index - 1].score, self.settings.scene_threshold
                )
                if index > 0
                else 0.0
            )
            scenes.append(
                Scene(
                    id=f"scene-{index + 1:04}",
                    start=round(start, 3),
                    end=round(end, 3),
                    duration=round(end - start, 3),
                    visual_score=round(start_visual_score, 4),
                    dominant_activity=context.dominant_activity,
                    activities=context.activities,
                    contexts=context.contexts,
                    mood=context.mood,
                    description=context.description,
                    transcript=transcript,
                )
            )
            progress(
                "Building semantic scenes",
                0.40 + 0.30 * ((index + 1) / max(len(boundaries) - 1, 1)),
            )
        return scenes
