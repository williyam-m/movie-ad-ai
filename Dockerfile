FROM node:22-bookworm-slim AS frontend

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts eslint.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    MODEL_CPU_THREADS=2 \
    CHHONDO_DATA_DIR=/data \
    HF_HOME=/data/hf-cache \
    ENABLE_ASR=true \
    ENABLE_VLM=true \
    ENABLE_SEMANTIC_MODEL=true \
    PORT=7860

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-core.txt requirements-models.txt requirements.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchvision==0.22.1 \
    && pip install -r requirements.txt

RUN useradd --create-home --uid 1000 user \
    && mkdir -p /data \
    && chown -R user:user /data /app

COPY --chown=user:user backend ./backend
COPY --chown=user:user scripts ./scripts
COPY --chown=user:user data ./data
COPY --from=frontend --chown=user:user /app/dist ./dist

USER user
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)"

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--proxy-headers"]