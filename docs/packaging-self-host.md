# Self-Host Guide — BYO-Compute, BYO-Key

media-pipeline is a **private, local-first AI DAM**. You run it on your own
hardware, against your own library, with your own compute and your own API keys.
It never hosts your media and makes no external call unless you opt into a remote
route. This guide covers a self-hosted install.

> **License:** AGPLv3 (`LICENSE`). Contributions require the `CLA.md` sign-off.
> A commercial **Pro** license unlocks software features only (see
> [Pro features](#pro-features)) — it is never a content gate. Uncensored
> capability is free and core.

## Core principles

| Principle | What it means |
|---|---|
| **BYO-compute** | Models run on *your* GPU/MPS box, or on a rented endpoint you control. No compute is bundled or hosted for you. |
| **BYO-key** | The only external API is OpenRouter, used only when you opt into a remote inference/vision route. Keys come from your env, never baked in. |
| **No bundled weights** | The image ships code, not model weights. Weights are pulled at runtime on first use, so each model's license is respected and the image stays small. |
| **Your media stays yours** | The content library + `data/catalog.db` are bind-mounted from the host. Nothing is copied into the image; SQLite is the single source of truth and only the local writer touches it. |

## Requirements

- **Docker + Docker Compose** (the slim path), or a native Python 3.14 install
  for the Apple-MLX vision tier (MLX does not run inside a Linux container).
- A **content library** directory (your images/video) and a **data** directory
  (holds `catalog.db`, caches, the TurboVec index).
- **Compute**, one of:
  - *Local*: an Apple-Silicon (MPS) or NVIDIA box for the on-box tiers
    (`local_mps` backend). For the MLX VLM caption tier, use the native install.
  - *Rented/remote*: a vLLM / SGLang / Triton / LitServe endpoint you control
    (`rented_metal` backend) — set its URL in `config.yaml`.
- Optional: an **OpenRouter API key** if you opt into a remote route.

## Quick start (Docker)

```bash
# 1. Clone and enter.
git clone <your-fork-or-source> media-pipeline && cd media-pipeline

# 2. Point at your library + data dirs and (optionally) your key.
cat > .env <<'EOF'
MEDIA_PIPELINE_CONTENT=/absolute/path/to/your/library
MEDIA_PIPELINE_DATA=/absolute/path/to/your/data
# Optional — only if you opt into a remote inference/vision route:
OPENROUTER_API_KEY=
# Optional — Pro license token (offline check, no phone-home):
MEDIA_PIPELINE_LICENSE=
EOF

# 3. Build + run. Default build is slim (no ML wheels); see "Compute" below.
docker compose up -d --build

# 4. Open the app.
open http://127.0.0.1:8000
```

The slim image runs the API + orchestration layer and talks to a BYO compute
backend. For an all-in-one local-compute box, build with the ML wheels:

```bash
docker compose build --build-arg INSTALL_ML=1
```

## Choosing a compute backend

Compute routing lives in `config.yaml` under the `compute:` block. Each of the
four capabilities — `embed`, `tag`, `caption`, `detect` — is routed to a named
backend. Swap backends by editing values only; no code change.

```yaml
compute:
  routes:
    embed: local_mps      # or rented_metal
    tag: local_mps
    caption: local_mps
    detect: local_mps
  backends:
    local_mps:
      type: local_mps     # on-box tiers; privacy=local, realtime
    rented_metal:
      type: rented_metal  # your vLLM/SGLang/Triton endpoint; privacy=private-infra, batch
      base_url: "http://your-rented-box:8000"
      api_key: null        # or read from your secrets env at call site
      timeout: 120
```

**Privacy gate:** the dispatcher refuses to route an uncensored job to a
`hosted-moderated` backend. Local (`local_mps`) and your-own-infra
(`rented_metal`) are always allowed; only pixel bytes ever leave the box, and
only for a backend you opted into. Paths and filenames never leave.

## Personalization (optional, local)

Two no-GPU personalization features run over your already-stored SigLIP vectors:

- **Few-shot linear probe** — give a handful of positive + negative example
  image ids and the probe scores every image; preview, then optionally tag
  matches (`tag_source="probe"`). Dry-run is the default.
- **Active-learning queue** — uses your existing keep/reject flags
  (`flag_action`) to propose the next images worth labeling (the ones the probe
  is least sure about).

API (after the personalize router is wired in `webui/main.py`):

```
POST /api/personalize/probe/preview          {pos_ids, neg_ids, threshold?, sample?}
POST /api/personalize/probe/apply            {..., category, value, dry_run?}
GET  /api/personalize/active-learning/next?count=N
```

These are numpy-only, run locally, and never call out. LoRA fine-tuning (rungs
3–4) is out of scope for the self-host build.

## Backups

`data/catalog.db` is the source of truth and uses WAL — a plain `cp` is unsafe.
Always back up with the WAL-safe script before any schema change:

```bash
bash scripts/backup_db.sh   # sqlite3 .backup + integrity_check + gzip
```

## Pro features

A Pro license (token in `MEDIA_PIPELINE_LICENSE` or a `license.key` file in the
project root) unlocks *software capabilities*, checked **offline** — there is no
phone-home and no content gate:

- `bulk_export`
- `remote_compute_routing`
- `priority_support`

Community (the default, no token) includes the full DAM, all four tiers, search,
and uncensored capability. See `pipeline/licensing.py`.

## Security notes

- Bind the port to `127.0.0.1` (or a Tailscale/WireGuard interface) — do not
  expose the API to the public internet without an auth proxy.
- Keep the content volume read-only (`:ro`) once your library is normalized.
- Secrets come from the env / `.env` file, never from a committed file.
