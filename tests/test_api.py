import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


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
