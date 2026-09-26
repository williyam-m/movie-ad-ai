---
title: Movie Ad AI
emoji: 🎬
colorFrom: red
colorTo: gray
sdk: static
app_build_command: cd frontend && npm ci && VITE_STATIC_SPACE=true npm run build
app_file: frontend/dist/index.html
pinned: false
---

# Movie Ad AI

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI 0.141](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Pydantic 2](https://img.shields.io/badge/Pydantic-2-E92063?logo=pydantic&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)
![TypeScript 6](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-scene%20%2B%20silence-007808?logo=ffmpeg&logoColor=white)
![SmolVLM2 256M](https://img.shields.io/badge/VLM-SmolVLM2%20256M-FFD21E)
![faster-whisper tiny](https://img.shields.io/badge/ASR-faster--whisper%20tiny-4B8BBE)
![MiniLM L12](https://img.shields.io/badge/Embeddings-MiniLM%20L12-FF6F00)
![Docker](https://img.shields.io/badge/Deploy-Docker%20Space-2496ED?logo=docker&logoColor=white)

Context-aware scene segmentation and intelligent ad placement for long-form Bengali video. Movie Ad AI finds natural interruption points, applies explicit pacing rules, rejects unsafe brand contexts, emits VMAP 1.0 with inline VAST 4.2, and demonstrates the result in a player that cuts to the ad and resumes the programme.

[Live Hugging Face Space](https://williyam-m-movie-ad-ai.hf.space) · [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md)

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

| Layer | Technology | Role |
| --- | --- | --- |
| Structural evidence | FFprobe and FFmpeg | Duration, scene-change scores, midpoint frames, and silence intervals |
| Speech timing | `faster-whisper/tiny` on CTranslate2 int8 | Bengali utterance intervals when no timed subtitle sidecar exists |
| Visual language model | `HuggingFaceTB/SmolVLM2-256M-Video-Instruct` | Representative-frame activity, mood, description, and safety context |
| Semantic retrieval | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Normalized multilingual scene-to-catalogue similarity |
| Policy and API | FastAPI, Pydantic, pure Python scoring | Input validation, hard safety gates, pacing, jobs, and auditable output |
| Workbench | React 19, TypeScript, Vite, Lucide | Upload controls, progress, decision inspection, and ad-resume playback |

Models load lazily. If any model is unavailable, the job is marked degraded and uses a conservative transcript/lexical fallback; silence and negative-context hard gates remain active.

## Execution path

1. **Bounded ingest:** FastAPI validates the container suffix and MIME type, then writes multipart input in 1 MiB chunks to a random job directory. The transfer is terminated above 400 MiB; catalogue JSON is separately capped at 512 KiB and validated with Pydantic.
2. **Deterministic evidence:** FFprobe reads programme duration. FFmpeg emits scene-change metadata and `silencedetect` intervals. Cuts closer than 2.5 seconds are merged by keeping the strongest edit.
3. **Dialogue map:** a timed `.srt` sidecar takes priority for the generated demo. Other videos use faster-whisper tiny with VAD, Bengali decoding, word timestamps, and two CPU threads. Speech overlap is a hard rejection, never a ranking penalty.
4. **Bounded VLM context:** one 512-pixel midpoint frame per eligible scene is sent to SmolVLM2 for structured activity, mood, description, and safety labels. Visual work stops after `MAX_VLM_SCENES`, when VLM is disabled, or immediately after a model failure.
5. **Safety and matching:** each boundary combines visual change, local silence, semantic shift, and edge distance only after hard eligibility checks pass. MiniLM embeds free-form catalogue data; a matching negative context removes a brand before the weighted activity ranking runs.
6. **Pacing and delivery:** safe, matchable candidates are selected under minimum-gap, breaks-per-hour, edge-margin, and ad-load limits. The worker writes a complete debug trace plus VMAP 1.0 with inline VAST 4.2, then the React player pauses content, plays the creative, and resumes.

### Lightweight execution choices

- API startup creates directories and validates the small default catalogue only; demo video and creatives are generated on the first demo request.
- ASR, VLM, and embedding weights are all loaded on first use and retained for later jobs.
- Frame extraction is skipped when no VLM can consume a frame, including after a VLM load failure.
- One analysis worker and two model threads bound CPU and memory pressure on the Space profile.
- The UI uses one adaptive status request at a time instead of overlapping interval polls.
- Every model layer has a deterministic fallback, so model download failure does not make the API unavailable.

## Run locally

Prerequisites: Python 3.11, Node.js 22, npm, and FFmpeg with `ffprobe` recommended.

```bash
cd frontend
npm ci
npm run build
cd ..

python3.11 -m venv .venv
. .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu \
  torch==2.7.1 torchvision==0.22.1
pip install -r requirements.txt

ENABLE_ASR=false \
ENABLE_VLM=false \
ENABLE_SEMANTIC_MODEL=false \
uvicorn backend.app:app --host 0.0.0.0 --port 7860
```

Open `http://localhost:7860`. The deterministic profile still performs real FFmpeg segmentation, silence detection, subtitle timing, safety scoring, pacing, matching, VMAP generation, and playback.

For the full model profile on CPU, use the same installation above and enable the models:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 7860
```

The first model-backed analysis downloads weights into `HF_HOME`; later jobs reuse them.

For frontend hot reload, run the API on port 7860 and `npm --prefix frontend run dev` in another terminal. Vite proxies `/api` and `/media` to FastAPI.

## Test

```bash
python -m ruff check backend scripts tests
python -m pytest
npm --prefix frontend run lint
npm --prefix frontend run build
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

The public Hugging Face deployment uses the free Static SDK. It serves a verified analysis snapshot with programme/ad playback, policy controls, VMAP export, debug JSON, and the full decision inspector. Video upload and new model inference require the Docker profile because Static Spaces do not run Python, FFmpeg, or model processes.

```bash
hf auth login --add-to-git-credential
hf repos create williyam-m/movie-ad-ai --type space --sdk static
git remote set-url space https://huggingface.co/spaces/williyam-m/movie-ad-ai
git push space main
```

For a compute-backed deployment, change the Space metadata to `sdk: docker`, set `PUBLIC_BASE_URL=https://williyam-m-movie-ad-ai.hf.space`, and deploy with the included Dockerfile. New Docker Spaces require an eligible paid Hugging Face plan.

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for model profiles, health checks, limits, and incident handling.

## Repository layout

```text
backend/        FastAPI, media evidence, ML adapters, policy, VMAP
data/           Validated synthetic brand catalogue
docs/           Architecture and production operations
frontend/       React/Vite source, package manifests, configs, and static assets
scripts/        Reproducible demo video/ad generator
tests/          Safety, matching, integration, and API tests
Dockerfile      Hugging Face CPU Space image
```

## Design boundaries

- Movie Ad AI does not infer that an ad must exist; safety can produce an empty schedule.
- The in-memory queue is intentionally single-worker for a 2-vCPU Space. For multi-replica production, replace it with durable object storage and a queue without changing scoring contracts.
- Generated demo visuals validate the workflow and avoid copyrighted drama footage. They are not a scene-quality benchmark.
- Automated semantic labels are advisory evidence. Hard audio and negative-context controls are deterministic and visible in debug output.