# Platform support matrix

What runs where, and why. The single `requirements.txt` uses environment
markers so `pip install -r requirements.txt` installs the right subset on each
platform — there is **no separate "core" requirements file**.

## Platforms

| Platform | Install | Tier | Notes |
|---|---|---|---|
| **macOS Apple Silicon (arm64)** | `pip install -r requirements.txt` | **Full** | Primary target. All tiers + local MLX captioning + ANN vector search. |
| **Linux x86_64 + NVIDIA** | `pip install -r requirements.txt` | **Full ML** (no local MLX) | GPU offload box. torch/transformers/onnxruntime via CUDA wheels. `turbovec`/`mlx-vlm` are skipped (not needed there). |
| **macOS Intel (x86_64)** | `pip install -r requirements.txt` | **Core** | Heavy ML wheels skip automatically (see below). Server + UI + browse + keyword/caption search work; ML tiers do not run locally. |
| **Linux x86_64, no GPU** | `pip install -r requirements.txt` | Core + CPU ML | torch CPU installs; tagging/embedding run (slowly). No `turbovec`/`mlx-vlm`. |

## Feature × platform

| Feature | Apple Silicon | Intel mac | Needs |
|---|---|---|---|
| Browse / inspect / collections / notes | ✅ | ✅ | core (SQLite) |
| Keyword + caption search (FTS) | ✅ | ✅ | core (SQLite FTS) |
| Dashboard / facets / pipeline stats | ✅ | ✅ | core |
| Find-similar + semantic vector search | ✅ | ⚠️ degrades | `turbovec` ANN wheel (Apple-Silicon) — lazy-imported; a clean error / fallback when absent |
| Tagging (Tier 0) / embedding (Tier 1) / NudeNet (Tier 3) | ✅ | ❌ | `torch` + `onnxruntime` (no x86_64-macOS torch wheel) — run on Apple Silicon or a GPU box |
| Local captioning (Tier 2) | ✅ | ❌ | `mlx-vlm` — Apple MLX is Apple-Silicon-only |
| Captioning via OpenRouter (opt-in) | ✅ | ✅ | network only |

## Why the markers

Three deps cannot install (or cannot run) on x86_64 macOS, so they carry env
markers in `requirements.txt`:

- **`torch` (+ `transformers`, `onnxruntime`, `nudenet`, `huggingface_hub`)** —
  PyTorch dropped x86_64-macOS wheels; there is no torch to install on an Intel
  Mac. Marker installs them on Apple Silicon **and** Linux, skips x86_64-macOS.
- **`mlx-vlm`** — Apple MLX targets the Apple GPU; no non-arm-macOS build exists.
- **`turbovec`** — ships an Apple-Silicon ANN wheel; gated to `arm64`.

The app is built to **degrade, not crash**, without them: `webui.main` imports
with the entire ML stack absent (verified), the ANN backend is lazy-imported
(`pipeline/tier1_embedder._turbovec`), and vector search falls back when vectors
are unavailable. CI proves this — the `x86_64 (Intel)` lane installs the marker
subset and runs a core import smoke + functional tests (`.github/workflows/ci.yml`).

## Distribution / packaging (Wave 4)

Building + unsigned local testing of an Intel bundle needs **no certificates**;
signing/notarization is required only to distribute to other machines. See
`docs/status/DEFERRED.md` (D-SIGN) and the signing playbook.
