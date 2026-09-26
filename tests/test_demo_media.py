from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from backend.config import Settings
from scripts.generate_demo_media import ensure_demo_media


def test_concurrent_demo_requests_generate_media_once(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime")
    build_started = Event()
    release_build = Event()
    demo_builds: list[Path] = []

    def build_demo(output_path: Path, _: Settings) -> None:
        demo_builds.append(output_path)
        build_started.set()
        assert release_build.wait(timeout=2)
        output_path.write_bytes(b"complete demo")

    def build_ad(
        output_path: Path, _: dict[str, object], _index: int, _settings: Settings
    ) -> None:
        output_path.write_bytes(b"complete ad")

    with (
        patch("scripts.generate_demo_media._build_demo_video", build_demo),
        patch("scripts.generate_demo_media._build_ad", build_ad),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(ensure_demo_media, settings)
        assert build_started.wait(timeout=2)
        second = executor.submit(ensure_demo_media, settings)
        release_build.set()
        generated_paths = [first.result(timeout=2), second.result(timeout=2)]

    assert generated_paths[0] == generated_paths[1]
    assert generated_paths[0].read_bytes() == b"complete demo"
    assert len(demo_builds) == 1
    assert not list(settings.data_dir.rglob("*.partial.mp4"))