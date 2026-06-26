# media-pipeline — self-host image.
#
# Philosophy (locked in the platform-evolution spec):
#   - BYO-COMPUTE: this image carries the app + Python deps, NOT model weights.
#     Weights (SigLIP, taggers, NudeNet, VLM) are pulled at RUNTIME on first use,
#     so the per-model license is respected and the image stays small. Heavy ML
#     wheels (turbovec/onnxruntime/mlx) are installed only when you build with
#     the `full` profile (see ARG INSTALL_ML below) — the default is the slim
#     API/orchestration layer that talks to a BYO compute backend.
#   - BYO-KEY: the only external API is OpenRouter, and only when opt-in. Keys
#     come from the runtime env (see docker-compose.yml), never baked into a layer.
#   - NEVER hosts user media: the content library + catalog.db are bind-mounted
#     from the host at runtime; nothing is copied into the image.
#
# Build (slim, default):   docker build -t media-pipeline .
# Build (with ML wheels):  docker build --build-arg INSTALL_ML=1 -t media-pipeline:full .

FROM python:3.14-slim AS base

# Runtime deps: libvec0 (sqlite-vec) is loaded by the app; ffmpeg/exiftool are
# used by the video + metadata paths. Build tools are dropped after pip install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libimage-exiftool-perl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching. INSTALL_ML toggles the heavy ML
# wheels (turbovec/onnxruntime/mlx) — off by default so the slim image builds
# fast and small; turn it on for an all-in-one local-compute box.
ARG INSTALL_ML=0
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && if [ "$INSTALL_ML" = "1" ]; then \
         python -m pip install --no-cache-dir -r requirements.txt; \
       else \
         python -m pip install --no-cache-dir \
            fastapi uvicorn[standard] sqlalchemy pyyaml pydantic numpy pillow; \
       fi

# App source. Content library + data/catalog.db are NOT copied — they are
# bind-mounted at runtime (see docker-compose.yml).
COPY pipeline/ ./pipeline/
COPY webui/ ./webui/
COPY scripts/ ./scripts/
COPY config.yaml ./config.yaml
COPY LICENSE CLA.md ./

# Non-root runtime user; the mounted data dir must be writable by this uid.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# The app reads host/port from config.yaml. Launch uvicorn against the FastAPI
# app object directly (webui/main.py defines `app`).
CMD ["python", "-m", "uvicorn", "webui.main:app", "--host", "0.0.0.0", "--port", "8000"]
