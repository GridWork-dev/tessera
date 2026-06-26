# Dockerfile.h100 — build note

Pre-baked CUDA image for the H100 offload run (all 4 tiers). Baking weights +
deps cuts per-rental spin-up from ~20 min (re-pulling 4 models + installing
vLLM/torch) to a few minutes.

## What's inside

| Component | Tier | Pinned |
|---|---|---|
| `torch==2.6.0` (cu124) + `transformers==5.12.1` | 1 (SigLIP SO400M) | YES — match the local venv for embedding parity |
| `onnxruntime-gpu` (CUDA + TensorRT EP) | 0 (WD-EVA02 + JoyTag) | floats; pin if parity drifts |
| `vllm` | 2 (JoyCaption Beta One) | floats |
| `nudenet` | 3 | floats |
| `google/siglip-so400m-patch14-384` weights | 1 | baked into HF cache |
| `fancyfeast/llama-joycaption-beta-one-hf-llava` weights | 2 | baked into HF cache |
| `wd-eva02/` + `joytag/` ONNX + labels | 0 | COPY from `docker/models/` |

## Before building — stage the Tier-0 ONNX weights

The big `.onnx` files are gitignored and box-only. Copy them from the Mac into
the build context so `COPY docker/models/ /opt/models/` finds them:

```
mkdir -p docker/models/wd-eva02 docker/models/joytag
cp models/wd-eva02/model.onnx        docker/models/wd-eva02/
cp models/wd-eva02/selected_tags.csv docker/models/wd-eva02/
cp models/joytag/model.onnx          docker/models/joytag/
cp models/joytag/top_tags.txt        docker/models/joytag/
```

`docker/models/` should be in `.gitignore` (it's weights). NudeNet downloads its
own small ONNX on first `NudeDetector()` if not present, so it's optional here.

## Build + publish

```
# build (on a CUDA-capable host or buildx; the HF snapshot_download step needs net)
docker build -f docker/Dockerfile.h100 -t <registry>/mp-h100:latest .

# push to a registry the rented box can pull from (Docker Hub / GHCR private)
docker push <registry>/mp-h100:latest
```

Vast.ai launches instances directly from a Docker image, so point the offer's
image field at `<registry>/mp-h100:latest` (private registry creds set in the
Vast template). Alternatively run a vanilla CUDA image and `pip install` on-box —
slower, and re-pulls weights each rental.

## Parity caveat

`transformers` / `torch` versions drive SigLIP `pooler_output`. If the local
venv ever upgrades transformers, bump the pin here too and re-run
`validate_h100_parity.py` on a pilot before the full run — a version skew can
shift embeddings past the 1e-4 tolerance.
