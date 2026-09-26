# Operations and Deployment

## Runtime profile

The Docker image is sized for the Hugging Face CPU Basic environment:

- 2 vCPU
- 16 GB RAM
- 50 GB disk
- one Uvicorn process
- one analysis worker
- two model/OMP threads
- lazy model downloads under `/data/hf-cache`

The frontend is compiled in a Node 22 build stage. The runtime image contains Python 3.11, FFmpeg/ffprobe, Noto and DejaVu fonts, CPU-only PyTorch, FastAPI, and the three small model adapters. It runs as non-root UID 1000.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | `http://localhost:7860` | Absolute VMAP creative and impression origin |
| `MOVIE_AD_AI_DATA_DIR` | `<repo>/runtime` | Job, demo, creative, and model-writable root |
| `MAX_UPLOAD_BYTES` | `419430400` | Streaming upload limit (400 MiB) |
| `ENABLE_ASR` | `true` | Enable faster-whisper Bengali timing |
| `ASR_MODEL_ID` | `tiny` | CTranslate2 Whisper checkpoint |
| `ENABLE_VLM` | `true` | Enable visual scene descriptions |
| `VLM_MODEL_ID` | `HuggingFaceTB/SmolVLM2-256M-Video-Instruct` | Visual model repository |
| `MAX_VLM_SCENES` | `36` | Bound visual inference per job |
| `ENABLE_SEMANTIC_MODEL` | `true` | Enable multilingual embedding similarity |
| `SEMANTIC_MODEL_ID` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embedding repository |
| `MODEL_CPU_THREADS` | `2` | Torch and ASR CPU thread cap |
| `SCENE_THRESHOLD` | `0.18` | FFmpeg visual cut threshold |
| `MAX_ANALYSIS_SECONDS` | `7200` | FFmpeg subprocess timeout |

## Deployment checklist

1. Run the local quality gate.
2. Ensure the Space SDK is Docker and port is 7860.
3. Set `PUBLIC_BASE_URL` to the final `https://<owner>-<space>.hf.space` origin.
4. Push source; do not upload `runtime`, `.venv`, `dist`, or model caches.
5. Watch the Space build logs until the health endpoint returns 200.
6. Trigger `/api/demo` and poll the job until `completed`.
7. Fetch the VMAP, debug JSON, programme MP4, and selected creative.
8. Play through the marker and verify the programme resumes.

## Health and verification

```bash
curl -fsS https://williyam-movie-ad-ai.hf.space/api/health

JOB_ID=$(curl -fsS -X POST \
  -H 'content-type: application/json' \
  -d '{"max_breaks_per_hour":4,"min_gap_seconds":30,"max_ad_load_percent":8}' \
  https://williyam-movie-ad-ai.hf.space/api/demo | python -c \
  'import json,sys; print(json.load(sys.stdin)["id"])')

curl -fsS "https://williyam-movie-ad-ai.hf.space/api/jobs/$JOB_ID"
```

Expected sample characteristics in deterministic mode are five scenes, four visual candidates, four safe boundaries, one scheduled break, and ad load below 8%. Model-backed context may change semantic scores and the winning safe timestamp, but it must not violate hard gates.

## Model cold start

The UI and health endpoint are available before model weights load. The first real upload can take longer while the model Hub cache fills. The generated demo includes a timed subtitle sidecar, so ASR is not needed to demonstrate dialogue safety; VLM and semantic models still load when enabled.

If model Hub access fails, the job completes with `models.degraded=true` and explanatory notes. It does not bypass silence, dialogue, pacing, or negative-context rules.

For a fast deterministic smoke test, temporarily set all three `ENABLE_*` variables to `false`. Restore them for judged model-backed runs.

## Capacity and limits

- One analysis runs at a time; additional requests remain queued in process.
- A 400 MiB upload limit protects disk; inputs should still be compressed to reduce queue time.
- VLM inference is bounded to 36 scenes. Remaining scenes use transcript context.
- Each completed job retains source and artefacts until the container restarts. Persistent production deployments need an explicit retention job.
- The in-memory job table does not survive a process restart.

## Failure triage

### Job fails during metadata or scene detection

Check that the source is a supported container with at least one video stream. FFmpeg's final stderr lines are stored as the bounded job error.

### Zero safe boundaries

Inspect `debug.json`. This is often correct: speech overlap, insufficient silence, edge margins, or the interruptibility threshold can reject every cut. Do not lower a hard gate merely to force inventory.

### Safe boundaries but zero scheduled breaks

Check pacing limits and `blocked_brands`. The ad-load cap may allow zero creatives for very short media, or every brand may have a negative-context conflict.

### Space is healthy but first job is slow

Inspect build/runtime logs for model downloads. Confirm `/data` is writable and model IDs are accessible. Subsequent requests should reuse `HF_HOME`.

### Out of memory

Lower `MAX_VLM_SCENES`, disable VLM temporarily, and confirm only one Uvicorn worker is running. Do not add parallel job workers on the 2-vCPU profile.

## Observability

Current observability surfaces are structured job status, stage/progress, bounded errors, model degradation metadata, and complete decision JSON. A production extension should add request IDs, JSON logs, per-stage latency histograms, queue depth, model-load duration, rejection-reason counts, and storage retention metrics.

Never log uploaded transcript text, catalogue secrets, tokens, or full local paths in a shared environment.