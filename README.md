---
title: Chhondo Movie Ad AI
emoji: 🎬
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Chhondo

Context-aware scene segmentation and intelligent ad placement for long-form Bengali video. Chhondo finds natural interruption points, applies explicit pacing rules, rejects unsafe brand contexts, emits VMAP 1.0 with inline VAST 4.2, and demonstrates the result in a player that cuts to the ad and resumes the programme.

[Live Hugging Face Space](https://williyam-movie-ad-ai.hf.space) · [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md)

## What it guarantees

- **Where:** a visual boundary must also pass a silence floor and a speech-overlap hard gate. A high visual score cannot rescue a mid-dialogue cut.
- **Whether:** break selection enforces maximum breaks per hour, minimum spacing, programme edge margins, minimum interruptibility, and maximum ad load.
- **What:** brands are loaded from JSON, dominant activity has the largest ranking weight, and every matching `negative_contexts` entry removes that brand before ranking.
- **No forced ad:** if no boundary or brand is safe, the valid outcome is zero breaks.
- **Open catalogue:** a ninth or later brand requires only a schema-valid JSON record, not a code change.

All bundled brands and creatives are synthetic. No real company names are substituted into the catalogue.

## System at a glance

```mermaid
flowchart LR
    V[Video upload] --> F[FFmpeg evidence]
    F --> S[Semantic scenes]
    F --> D[Dialogue and silence gates]
    S --> C[Boundary scoring]
    D --> C
    C --> P[Pacing policy]
    S --> B[Data-driven brand matcher]
    P --> B
    B --> M[VMAP + debug JSON]
    M --> R[React ad-resume player]
```

The default CPU profile uses:

- `HuggingFaceTB/SmolVLM2-256M-Video-Instruct` for representative-frame context
- `faster-whisper/tiny` with int8 CPU inference for Bengali speech timing
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for multilingual catalogue similarity
- FFmpeg scene-change and silence evidence as deterministic anchors

Models load lazily. If any model is unavailable, the job is marked degraded and uses a conservative transcript/lexical fallback; silence and negative-context hard gates remain active.

## Run locally

Prerequisites: Python 3.11, Node.js 22, npm, and FFmpeg with `ffprobe` recommended.

```bash
npm ci
npm run build

python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements-core.txt

ENABLE_ASR=false \
ENABLE_VLM=false \
ENABLE_SEMANTIC_MODEL=false \
uvicorn backend.app:app --host 0.0.0.0 --port 7860
```

Open `http://localhost:7860`. The deterministic profile still performs real FFmpeg segmentation, silence detection, subtitle timing, safety scoring, pacing, matching, VMAP generation, and playback.

For the full model profile on CPU:

```bash
pip install --index-url https://download.pytorch.org/whl/cpu \
  torch==2.7.1 torchvision==0.22.1
pip install -r requirements.txt
uvicorn backend.app:app --host 0.0.0.0 --port 7860
```

The first model-backed analysis downloads weights into `HF_HOME`; later jobs reuse them.

For frontend hot reload, run the API on port 7860 and `npm run dev` in another terminal. Vite proxies `/api` and `/media` to FastAPI.

## Test

```bash
python -m ruff check backend scripts tests
python -m pytest
npm run lint
npm run build
```

The suite covers mid-dialogue rejection, silence gating, funeral/food exclusion, an all-brands-blocked no-ad outcome, an unseen ninth brand, pacing limits, generated-video segmentation, VMAP parsing, asynchronous API jobs, and media delivery.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Service and configured model status |
| `GET` | `/api/catalogue` | Public fields for the bundled synthetic brands |
| `POST` | `/api/demo` | Queue analysis of the generated sample |
| `POST` | `/api/jobs` | Stream a video and optional JSON catalogue into a job |
| `GET` | `/api/jobs/{id}` | Poll progress and retrieve the result |
| `GET` | `/api/jobs/{id}/manifest.vmap` | Download VMAP 1.0 with inline VAST 4.2 |
| `GET` | `/api/jobs/{id}/debug.json` | Download the complete auditable decision trace |

Upload fields are `video`, optional `catalogue`, `max_breaks_per_hour`, `min_gap_seconds`, and `max_ad_load_percent`.

## Add an unseen brand

The catalogue accepts an object with a `brands` array. Matching uses only these fields:

```json
{
  "brands": [
    {
      "id": "new-brand",
      "name": "New Brand",
      "category": "optics",
      "description": "A synthetic compact telescope brand.",
      "tagline": "See farther tonight.",
      "color": "#5364A8",
      "target_activities": ["stargazing", "nature observation"],
      "positive_contexts": ["night sky", "curiosity"],
      "negative_contexts": ["funeral", "medical emergency", "violence"],
      "creative_path": "https://example.invalid/creative.mp4",
      "duration_seconds": 6
    }
  ]
}
```

`creative_path` must be HTTPS or an application-owned `/media/` path. IDs are unique, catalogue size is capped, and unknown fields are rejected.

## Deploy

The repository is a Docker Space. A push to the Hugging Face Space repository triggers the multi-stage build and exposes port 7860. The image runs as UID 1000, generates copyright-safe demo media at startup, and stores jobs/model cache under `/data`.

```bash
hf auth login
hf repo create movie-ad-ai --type space --space-sdk docker
git push space main
```

Set `PUBLIC_BASE_URL=https://williyam-movie-ad-ai.hf.space` in the Space variables so VMAP media and impression URLs are absolute.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for model profiles, health checks, limits, and incident handling.

## Repository layout

```text
backend/        FastAPI, media evidence, ML adapters, policy, VMAP
data/           Validated synthetic brand catalogue
docs/           Architecture and production operations
scripts/        Reproducible demo video/ad generator
src/            React workbench and ad-resume player
tests/          Safety, matching, integration, and API tests
Dockerfile      Hugging Face CPU Space image
```

## Design boundaries

- Chhondo does not infer that an ad must exist; safety can produce an empty schedule.
- The in-memory queue is intentionally single-worker for a 2-vCPU Space. For multi-replica production, replace it with durable object storage and a queue without changing scoring contracts.
- Generated demo visuals validate the workflow and avoid copyrighted drama footage. They are not a scene-quality benchmark.
- Automated semantic labels are advisory evidence. Hard audio and negative-context controls are deterministic and visible in debug output.