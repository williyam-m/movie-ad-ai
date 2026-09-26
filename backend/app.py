from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.catalogue import CatalogueError, load_catalogue, parse_catalogue_bytes
from backend.config import Settings
from backend.jobs import JobNotFoundError, JobStore
from backend.model_runtime import ModelRuntime
from backend.pipeline import VideoAnalysisPipeline
from backend.schemas import Brand, DemoRequest, JobRecord, PacingPolicy
from scripts.generate_demo_media import ensure_demo_media

LOGGER = logging.getLogger("movie_ad_ai")
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "application/octet-stream",
}
MAX_CATALOGUE_BYTES = 512 * 1024


async def _store_upload(
    upload: UploadFile, destination: Path, maximum_bytes: int
) -> None:
    total_bytes = 0
    maximum_megabytes = maximum_bytes // 1024 // 1024
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > maximum_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Upload exceeds the {maximum_megabytes} MB limit",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded video is empty")


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    active_settings.ensure_directories()
    supplied_demo_path = active_settings.demo_dir / "mohanagar.mp4"
    supplied_catalogue_path = active_settings.demo_dir / "brands.json"
    catalogue_path = (
        supplied_catalogue_path
        if supplied_demo_path.is_file() and supplied_catalogue_path.is_file()
        else active_settings.root_dir / "data" / "brands.json"
    )
    default_catalogue = load_catalogue(catalogue_path)
    store = JobStore()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="movie-ad-analysis"
    )
    models = ModelRuntime(active_settings)
    pipeline = VideoAnalysisPipeline(active_settings, models)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    application = FastAPI(
        title="Movie Ad AI",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.jobs = store
    application.state.executor = executor

    @application.middleware("http")
    async def security_headers(request: object, call_next: object) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' https: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self'; connect-src 'self'"
        )
        if str(getattr(request, "url", "")).find("/api/") >= 0:
            response.headers["Cache-Control"] = "no-store"
        return response

    def submit_job(
        record: JobRecord,
        source_path: Path,
        source_name: str,
        media_url: str,
        brands: list[Brand],
        policy: PacingPolicy,
    ) -> None:
        job_dir = active_settings.jobs_dir / record.id

        def run() -> None:
            try:
                result = pipeline.analyse(
                    job_id=record.id,
                    source_path=source_path,
                    source_name=source_name,
                    media_url=media_url,
                    brands=brands,
                    policy=policy,
                    job_dir=job_dir,
                    progress=lambda stage_name, value: store.progress(
                        record.id, stage_name, value
                    ),
                )
                store.complete(record.id, result)
            except Exception as error:
                LOGGER.exception("Analysis job %s failed", record.id)
                store.fail(record.id, error)

        executor.submit(run)

    @application.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "movie-ad-ai",
            "version": application.version,
            "models": {
                "visual": active_settings.vlm_model_id,
                "speech": f"faster-whisper/{active_settings.asr_model_id}",
                "semantics": active_settings.semantic_model_id,
            },
        }

    @application.get("/api/catalogue")
    async def catalogue() -> dict[str, list[dict[str, object]]]:
        return {
            "items": [
                brand.model_dump(exclude={"creative_path", "duration_seconds"})
                for brand in default_catalogue
            ]
        }

    @application.post(
        "/api/demo",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_demo(request: DemoRequest) -> JobRecord:
        demo_path = await asyncio.to_thread(ensure_demo_media, active_settings)
        record = store.create()
        submit_job(
            record,
            demo_path,
            demo_path.name,
            f"/media/demo/{demo_path.name}",
            default_catalogue,
            PacingPolicy(**request.model_dump()),
        )
        return record

    @application.post(
        "/api/jobs",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_job(
        video: Annotated[UploadFile, File(description="Long-form video")],
        catalogue_file: Annotated[UploadFile | None, File(alias="catalogue")] = None,
        max_breaks_per_hour: Annotated[int, Form(ge=1, le=12)] = 4,
        min_gap_seconds: Annotated[float, Form(ge=30, le=1800)] = 420,
        max_ad_load_percent: Annotated[float, Form(ge=1, le=20)] = 8,
    ) -> JobRecord:
        source_name = Path(video.filename or "upload.mp4").name
        suffix = Path(source_name).suffix.casefold()
        if (
            suffix not in ALLOWED_VIDEO_SUFFIXES
            or video.content_type not in ALLOWED_VIDEO_TYPES
        ):
            raise HTTPException(status_code=415, detail="Unsupported video format")

        brands = default_catalogue
        catalogue_content: bytes | None = None
        if catalogue_file is not None:
            catalogue_content = await catalogue_file.read(MAX_CATALOGUE_BYTES + 1)
            await catalogue_file.close()
            if len(catalogue_content) > MAX_CATALOGUE_BYTES:
                raise HTTPException(status_code=413, detail="Catalogue exceeds 512 KB")
            try:
                brands = parse_catalogue_bytes(catalogue_content)
            except CatalogueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

        record = store.create()
        job_dir = active_settings.jobs_dir / record.id
        source_path = job_dir / f"source{suffix}"
        await _store_upload(video, source_path, active_settings.max_upload_bytes)
        bundled_scene_context = (
            active_settings.root_dir
            / "data"
            / "demo"
            / f"{Path(source_name).stem.casefold()}.scenes.json"
        )
        if bundled_scene_context.is_file():
            shutil.copyfile(
                bundled_scene_context, source_path.with_suffix(".scenes.json")
            )
        if catalogue_content is not None:
            (job_dir / "catalogue.json").write_bytes(catalogue_content)
        media_url = f"/media/jobs/{record.id}/{source_path.name}"
        policy = PacingPolicy(
            max_breaks_per_hour=max_breaks_per_hour,
            min_gap_seconds=min_gap_seconds,
            max_ad_load_percent=max_ad_load_percent,
        )
        submit_job(record, source_path, source_name, media_url, brands, policy)
        return record

    @application.get("/api/jobs/{job_id}", response_model=JobRecord)
    async def get_job(job_id: str) -> JobRecord:
        try:
            return store.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Analysis job not found"
            ) from error

    def completed_artifact(job_id: str, filename: str, media_type: str) -> FileResponse:
        try:
            record = store.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Analysis job not found"
            ) from error
        if record.status != "completed":
            raise HTTPException(status_code=409, detail="Analysis is not complete")
        path = active_settings.jobs_dir / job_id / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Analysis artefact not found")
        return FileResponse(
            path,
            media_type=media_type,
            filename=f"{Path(record.result.source_name).stem}-{filename}",
        )

    @application.get("/api/jobs/{job_id}/manifest.vmap")
    async def get_manifest(job_id: str) -> FileResponse:
        return completed_artifact(job_id, "manifest.vmap", "application/xml")

    @application.get("/api/jobs/{job_id}/debug.json")
    async def get_debug(job_id: str) -> FileResponse:
        return completed_artifact(job_id, "debug.json", "application/json")

    @application.get("/api/impressions/{job_id}/{break_id}", status_code=204)
    async def impression(job_id: str, break_id: str) -> Response:
        try:
            store.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Analysis job not found"
            ) from error
        return Response(status_code=204, headers={"X-Break-Id": break_id})

    application.mount(
        "/media",
        StaticFiles(directory=str(active_settings.data_dir)),
        name="media",
    )
    application.mount(
        "/",
        StaticFiles(
            directory=str(active_settings.root_dir / "frontend" / "dist"),
            html=True,
            check_dir=False,
        ),
        name="frontend",
    )
    return application


app = create_app()
