from pathlib import Path
from xml.etree import ElementTree as ET

from backend.catalogue import load_catalogue
from backend.config import Settings
from backend.media import normalise_scene_change
from backend.model_runtime import ModelRuntime
from backend.pipeline import VideoAnalysisPipeline
from backend.schemas import PacingPolicy
from backend.vmap import VMAP_NAMESPACE
from scripts.generate_demo_media import ensure_demo_media


def test_scene_change_strength_is_calibrated_to_detection_threshold() -> None:
    assert normalise_scene_change(0.18, 0.18) == 0.5
    assert normalise_scene_change(0.36, 0.18) == 1.0
    assert normalise_scene_change(0.72, 0.18) == 1.0


def test_generated_demo_runs_end_to_end(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        enable_asr=False,
        enable_vlm=False,
        enable_semantic_model=False,
    )
    demo_path = ensure_demo_media(settings)
    brands = load_catalogue(settings.root_dir / "data" / "brands.json")
    job_dir = settings.jobs_dir / "integration-test"
    pipeline = VideoAnalysisPipeline(settings, ModelRuntime(settings))

    result = pipeline.analyse(
        job_id="integration-test",
        source_path=demo_path,
        source_name="movie-ad-ai-demo.mp4",
        media_url="/media/demo/movie-ad-ai-demo.mp4",
        brands=brands,
        policy=PacingPolicy(min_gap_seconds=30),
        job_dir=job_dir,
    )

    assert result.summary.scene_count == 5
    assert result.summary.candidate_count == 4
    assert result.summary.safe_candidate_count >= 3
    assert result.summary.break_count == 1
    assert result.summary.ad_load_percent <= result.policy.max_ad_load_percent
    assert all(
        not candidate.features.speech_overlap
        for candidate in result.candidates
        if candidate.is_safe
    )
    assert not (job_dir / "frames").exists()
    assert (job_dir / "debug.json").is_file()

    manifest_path = job_dir / "manifest.vmap"
    root = ET.fromstring(manifest_path.read_text(encoding="utf-8"))
    ad_breaks = root.findall(f"{{{VMAP_NAMESPACE}}}AdBreak")
    assert root.attrib["version"] == "1.0"
    assert len(ad_breaks) == result.summary.break_count
    assert ad_breaks[0].attrib["timeOffset"] == result.breaks[0].time_offset
