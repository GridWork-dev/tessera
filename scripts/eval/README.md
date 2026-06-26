# scripts/eval — model-variation evaluation

Reproducible eval recipes for comparing model backends **on a staging instance**,
never the live `catalog.db`. Stand up staging per
[`docs/runbooks/datasets-staging-session-prompt.md`](../../docs/runbooks/datasets-staging-session-prompt.md)
(isolated DB + content; the live catalog stays untouched).

> **Provenance:** the original ad-hoc eval scripts from the 2026-06-24 staging
> session were session-scratch and were not committed (now gone). This file
> preserves the **recipe + findings** so the comparisons can be re-run. The two
> bugs they surfaced are already fixed in shipped code (below). Reconstructing
> runnable drivers here is a clean follow-up — keep them dependency-light and
> skip-gracefully when a model/dep is absent (mirror `pipeline/faces/embedder.py`).

---

## 1. Captions — mlx-vlm vs Ollama

Compare the two Tier-2 caption backends (`pipeline/tier2_captioner.py`) on the
same staging images.

- **Result (114-image staging set):** both produced 114/114 captions; quality
  comparable for browse/search.
- **Gotcha found + fixed:** Ollama returned **HTTP 400 on high-resolution
  images**. Fix = **downscale the image before the call** and raise **`num_ctx`**
  enough to hold the image tokens. Without both, hi-res frames fail; with them,
  parity with mlx-vlm.
- mlx-vlm (Qwen2.5-VL / JoyCaption) is the on-box default; Ollama (`localhost:11434`)
  is the alternate. Keep the prompt + decode params identical across backends so
  only the model varies.

## 2. Rating — nsfw-2-mini vs NudeNet

Compare the rating *signal* (`pipeline/nsfw2mini.py`) against NudeNet region
metadata (`pipeline/tier3_nudenet.py`). NudeNet is **metadata only, never a gate**.

- **Bug found + fixed (shipped):** nsfw-2-mini's benign class is **`safe`**, not
  `Normal` as the model-card prose implies. The label map read `Normal`, so
  **109/114 clean images fell through to `unrated`**. Fixed in
  `pipeline/nsfw2mini.py::LABEL_TO_RATING` (`"safe": "sfw"`, commit `451044d`);
  unknown labels still map to `unrated` (never guess a rating).
- nsfw-2-mini is **additive** — it does not write `images.rating`. Swapping the
  rating signal from the WD-EVA02 head to this classifier is a deliberate,
  approval-gated central change (see `D-GPU-BACKFILL` in
  [`docs/status/DEFERRED.md`](../../docs/status/DEFERRED.md)).

---

## Guardrails

- **Staging only.** Never run eval writes against `data/catalog.db`. Back up first
  if a staging DB shares tooling: `bash scripts/backup_db.sh`.
- **Privacy.** Eval stays on-box; do not exfiltrate paths, filenames, or image
  content. Ollama + mlx-vlm are local; the only remote API in the project is
  OpenRouter (vision/inference), out of scope here.
