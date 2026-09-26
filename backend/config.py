from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = Path(os.getenv("MOVIE_AD_AI_DATA_DIR", ROOT_DIR / "runtime"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", 400 * 1024**2))
    ffmpeg_binary: str = os.getenv("FFMPEG_BINARY", "ffmpeg")
    ffprobe_binary: str | None = os.getenv("FFPROBE_BINARY") or shutil.which("ffprobe")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:7860").rstrip(
        "/"
    )
    enable_asr: bool = _environment_flag("ENABLE_ASR", True)
    enable_vlm: bool = _environment_flag("ENABLE_VLM", True)
    enable_semantic_model: bool = _environment_flag("ENABLE_SEMANTIC_MODEL", True)
    asr_model_id: str = os.getenv("ASR_MODEL_ID", "tiny")
    vlm_model_id: str = os.getenv(
        "VLM_MODEL_ID", "HuggingFaceTB/SmolVLM2-256M-Video-Instruct"
    )
    semantic_model_id: str = os.getenv(
        "SEMANTIC_MODEL_ID",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    max_vlm_scenes: int = int(os.getenv("MAX_VLM_SCENES", "36"))
    model_cpu_threads: int = int(os.getenv("MODEL_CPU_THREADS", "2"))
    scene_threshold: float = float(os.getenv("SCENE_THRESHOLD", "0.18"))
    max_analysis_seconds: int = int(os.getenv("MAX_ANALYSIS_SECONDS", "7200"))

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def demo_dir(self) -> Path:
        return self.data_dir / "demo"

    @property
    def ads_dir(self) -> Path:
        return self.data_dir / "ads"

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.jobs_dir, self.demo_dir, self.ads_dir):
            directory.mkdir(parents=True, exist_ok=True)
