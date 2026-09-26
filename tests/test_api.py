import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


def test_default_upload_limit_is_400_mib() -> None:
    assert Settings().max_upload_bytes == 400 * 1024**2


def test_startup_does_not_generate_demo_media(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime")

    with (
        patch("backend.app.ensure_demo_media") as generate_demo,
        TestClient(create_app(settings)) as client,
    ):
        assert client.get("/api/health").status_code == 200

    generate_demo.assert_not_called()


def test_demo_job_and_artifact_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        enable_asr=False,
        enable_vlm=False,
        enable_semantic_model=False,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        response = client.post(
            "/api/demo",
            json={
                "max_breaks_per_hour": 4,
                "min_gap_seconds": 30,
                "max_ad_load_percent": 8,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        deadline = time.monotonic() + 20
        payload = response.json()
        while (
            payload["status"] in {"queued", "running"} and time.monotonic() < deadline
        ):
            time.sleep(0.05)
            payload = client.get(f"/api/jobs/{job_id}").json()

        assert payload["status"] == "completed", payload.get("error")
        assert payload["result"]["summary"]["break_count"] == 1
        assert client.get(f"/api/jobs/{job_id}/manifest.vmap").status_code == 200
        assert client.get(f"/api/jobs/{job_id}/debug.json").status_code == 200
        assert client.get(payload["result"]["media_url"]).status_code == 200


def test_rejects_unsupported_upload(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        enable_asr=False,
        enable_vlm=False,
        enable_semantic_model=False,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post(
            "/api/jobs",
            files={"video": ("payload.txt", b"not a video", "text/plain")},
        )
        assert response.status_code == 415


def test_rejects_upload_above_limit_and_removes_partial_file(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        max_upload_bytes=4,
        enable_asr=False,
        enable_vlm=False,
        enable_semantic_model=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/jobs",
            files={"video": ("oversized.mp4", b"12345", "video/mp4")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Upload exceeds the 0 MB limit"
    assert not list(settings.jobs_dir.rglob("source.mp4"))
