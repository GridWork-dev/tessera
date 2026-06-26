# ADR-0001: M5 Multi-Tier Tagging Architecture

> **Status:** ACCEPTED 2026-06-22
> **Supersedes:** NudeNet-as-gate model (ROADMAP.md Phase 1, NEXT_SESSION.md Phase 0.4)
> **Source:** M5 Hardware Analysis report (26.7KB, 2026-06-22) + gridwork-core survey +
> pi-workflow-engine review + git-hooks research, triaged this session.

## Context

The M5 report proposes a fundamental shift: the current pipeline tags only ~4% of the
catalog (542/13,924) and gates VLM tagging behind NudeNet. The user's intent is the
opposite — **every image gets comprehensive tags regardless of content.** NudeNet becomes
one metadata input, not a skip condition. This decision supersedes the old ROADMAP Phase 1
(NudeNet pre-filter to *reduce* VLM calls) and inverts it: tag everything, then use the
tags to filter.

Four research tracks were synthesized this session. M5 is the dominant architectural
change; the other three (gridwork conventions, pi-workflow-engine, git-hooks) are
smaller-scoped decisions folded in below.

## Decision: Full M5 tiered model

Adopt the four-tier pipeline. ALL tiers run on ALL images unconditionally.

```
Tier 0 (ALL):  WD EVA02-Large v3 + JoyTag   → structured multi-label tags (~100-200ms/img)
Tier 1 (ALL):  SigLIP SO400M                  → 1152-dim vectors → TurboVec index (~20ms/img)
Tier 2 (ALL):  JoyCaption Beta One / Qwen2.5-VL → free-text caption, uncensored (~10-30s/img)
Tier 3 (ALL):  NudeNet                        → bounding-box metadata JSON, NEVER a gate
```

### New pipeline layout

```
pipeline/
  tier0_tagger.py     # WD EVA02-Large + JoyTag → structured tags (MPS batch=64)
  tier1_embedder.py   # SigLIP SO400M → 1152-dim → TurboVec index  (corrected 2026-06-22: SO400M image embedding is 1152-dim, not 768)
  tier2_vlm.py        # JoyCaption/Qwen via mlx-vlm → captions (KV-prefix-cache)
  tier3_nudenet.py    # NudeNet regions → JSON column (metadata only)
  paths.py            # (existing) relative-path resolver
  batch_tag.py        # orchestrates all tiers on ALL images
```

### M5 hardware exploitation

- **Ollama ≥0.19** switches to MLX backend on M5 → ~2× VLM throughput, zero code change.
  Immediate action: `brew upgrade ollama`.
- **mlx-vlm** replaces the Ollama HTTP-API for VLM calls → cuts HTTP overhead, enables
  prompt KV-prefix-caching (same system prompt across a batch: ~21s → ~0.78s/img, 28×). (corrected 2026-06-23: 28× misattributed — it is same-image multi-turn vision-feature caching, not batch system-prompt reuse; realistic text-prefix gain ~1.2–2.4×, plan ~4–10s/img cold. See outputs/research/01-tier2-vlm.md)
- **PyTorch MPS stays** for SigLIP embedding (acceptable). Add `torch.compile(mode="reduce-overhead")`
  for Neural Engine access.
- **ARM NEON** path activates automatically for TurboVec on Apple Silicon.

### Expected throughput on M5 24GB (after optimization)

| Stage | Current | Optimized | Method |
|---|---|---|---|
| WD/JoyTag | not running | ~100-200 img/min | MPS batch=64 |
| SigLIP embed | ~5/min (broken) | ~25-50/min | MPS + torch.compile |
| TurboVec index | not running | ~1000+/min | ARM NEON |
| Qwen2.5-VL (Ollama) | ~1-2/min | ~2-4/min | Ollama 0.19 MLX |
| JoyCaption (mlx-vlm) | not running | ~2-4/min | mlx-vlm + prefix cache |

**Backfill strategy:** Tier 0 + Tier 1 first pass on all 32K images (~11h) gives
immediate full structured-tag + vector coverage. Tier 2 VLM captioning runs async
in background (bottleneck tier, ~7.5 days one-time if done serially — prioritize by
rating/person).

## Schema changes (DB-altering — requires explicit approval)

These will be executed in Phase 1, not now. Documented here to lock the shape.

```sql
-- 1. Tag provenance (avoid mixing classifier tags with VLM captions)
ALTER TABLE tags ADD COLUMN tag_source TEXT DEFAULT 'vlm';
  -- values: 'vlm' | 'joytag' | 'wd_tagger' | 'joycaption' | 'openrouter' | 'user'
ALTER TABLE tags ADD COLUMN confidence REAL;  -- already exists in model; ensure live

-- 2. Long-form captions (separate from keyword tags)
CREATE TABLE captions (
    id INTEGER PRIMARY KEY,
    image_id INTEGER REFERENCES images(id),
    model TEXT NOT NULL,        -- 'joycaption-alpha2' | 'qwen2.5-vl-7b-abliterated'
    caption TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_captions_image ON captions(image_id);

-- 3. NudeNet bounding-box metadata (NOT a tag)
ALTER TABLE images ADD COLUMN nudenet_regions TEXT;  -- JSON [{label,score,box}]
ALTER TABLE images ADD COLUMN nudenet_checked INTEGER DEFAULT 0;
```

**Per project rules:** always `cp data/catalog.db data/catalog.db.bak` before any schema
change. Phase 1 will apply these via `data/migrations/` SQL files.

## What we explicitly REJECT

| Proposal | Verdict | Why |
|---|---|---|
| **TurboQuant** (`0xSero/turboquant`) | ❌ SKIP | KV-cache compression needs vLLM+CUDA. M5/MPS unsupported. mlx-vlm prefix-cache gives the equivalent win locally. (corrected 2026-06-23: that prefix-cache win is ~1.2–2.4× text-prefix reuse, not the implied 28× — 28× is same-image multi-turn vision caching; see outputs/research/01-tier2-vlm.md) |
| **NudeNet as gate** | ❌ REJECT | Contradicts the tag-everything intent. Demoted to Tier-3 metadata. |
| **sqlite-vec as sole vector store** | ⚠️ DUAL-STORE | Keep sqlite-vec full-precision for rescore; add TurboVec as fast first-pass ANN. TurboVec discards full-precision after quantization. |

## Cross-track decision: embeddings store

**ADOPT TurboVec** (`pip install turbovec`) as the primary ANN index. It is the direct,
M5-relevant win from the TurboQuant research: Rust-native, ARM-NEON-optimized (12-20%
faster than FAISS on Apple Silicon), zero-training, compresses 1152-dim float32 vectors
16× (3072B → ~192B at 4-bit). Pattern: TurboVec fast first-pass → sqlite-vec float
rescore (binary-coarse + float-rescore).

This supersedes the old ROADMAP Phase 2 "sqlite-vec brute-force cosine" plan.

---

## Cross-track decisions (the other three research tracks)

These are smaller-scoped; folded in here so one doc captures all session decisions.

### gridwork-core conventions → TRIM heavily

Surveyed `~/files/code/gridwork-core` (Claude Code orchestration infra, team-scale).
Most of it is over-engineered for a solo local photo app. **Adopt only:**

| Convention | Action | Sketch |
|---|---|---|
| `outputs/` dir for AI artifacts | ✅ Adopt | `outputs/` at repo root, gitignore `outputs/*.md`, `.gitkeep` for `outputs/sessions/` |
| Dated session summaries | ✅ Adopt | After non-trivial work → `outputs/sessions/YYYY-MM-DD.md` (Decisions, Files touched, Blockers, Next) |
| "Done means evidence" rule | ✅ Adopt | Add to the project guidelines: before claiming done, paste `pytest` + `tsc` output |

**Skip:** 12-agent `workforce/`, 11-layer memory architecture, `skeleton-2.md` schema
enforcement, `identity/` directory, CI pipeline with 6 test suites, machine-state-as-code
(`system/`). All team-scale; Pi's built-in memory + pytest/tsc already cover the solo use case.

### pi-workflow-engine → BORROW patterns, do NOT install

Reviewed [timbrinded/pi-workflow-engine](https://github.com/timbrinded/pi-workflow-engine)
(cloned to `/tmp/pi-github-repos/`). It adds structured-output fan-out, `parallel()`/
`pipeline()` primitives, a live progress tree widget, usage aggregation over Pi's built-in
`subagent()`. Verdict: **not worth a new dependency for a solo photo-catalog app** — you
won't run adversarial multi-pass reviews often enough. Revisit if review cadence rises.

**Borrow these patterns** (already used informally this session):

- **Scope → Find → Verify → Synthesize** review shape. Independent verifier agents REFUTE/
  CONFIRM each finding — kills hallucinated review complaints.
- **Per-agent `thinkingLevel` pinning** (scope=medium, find=low, verify=low). Prevents a
  fan-out from inheriting an expensive global `xhigh`.
- **Diff-bound findings** to changed lines (`changedLines()` + `inDiff()` gate). Stops
  reviewers complaining about code you didn't touch.
- **Dedup after the barrier**, not during.

If installed later: `pi install npm:pi-workflow-engine` (global extension, no config file).

### git-hooks → ADOPT pre-commit framework

**Decision:** add `pre-commit` (Python framework) + ruff + tsc local hook. **Not husky**
(Python repo, no root package.json). Defer pytest to pre-push stage.

Config scaffolded at `.pre-commit-config.yaml` this session (see file). Key choices:

- `pre-commit-hooks` (trailing-ws, EOF-fixer, check-yaml/json, merge-conflict, private-key)
- `ruff-pre-commit` (`ruff-check --fix` + `ruff-format`) — pinned revisions, replaces Black+isort+Flake8
- `local` hook: `cd frontend && npx tsc -b --force` scoped to `frontend/**/*.{ts,tsx}`
- **Excluded from pre-commit:** pytest, full eslint (too slow per-commit → `make test` / pre-push)

Install: `brew install pre-commit && pre-commit install`. One-time `pre-commit run --all-files`.

---

## Architecture decision summary (durable — respect these)

| Decision | Detail |
|---|---|
| **Tag everything, no gates** | All tiers (0-3) run on all images. NudeNet is metadata, never a skip. |
| **TurboVec primary ANN** | sqlite-vec demoted to rescore store. Dual-store: TurboVec fast-pass + sqlite-vec float rescore. |
| **mlX-vlm over Ollama HTTP** | Direct Python inference, KV-prefix-cache for batch system-prompt reuse. Ollama kept as fallback. (corrected 2026-06-23: 28× misattributed — it is same-image multi-turn vision-feature caching, not batch system-prompt reuse; realistic text-prefix gain ~1.2–2.4×, plan ~4–10s/img cold. See outputs/research/01-tier2-vlm.md) |
| **Ollama ≥0.19** | MLX backend, free 2× VLM throughput. `brew upgrade ollama`. |
| **Captions separate from tags** | New `captions` table for free-text VLM output; keyword tags stay in `tags`. |
| **tag_source provenance** | Every tag records its model. Enables per-source filtering + audit. |
| **pre-commit over husky** | Python framework fits a Python-dominant polyglot repo. |
| **outputs/ for AI scratch** | Dated session summaries, gitignored. the project guidelines stays the map, not the territory. |

## References

- M5 report source: `~/Downloads/media-pipeline  M5 Hardware Analysis, Full Model Guide & TurboVec TurboQuant Integration.md`
- TurboVec: <https://techstartups.com/2026/06/06/google-shrinks-ai-memory-from-31gb-to-4gb-with-turbovec-beating-faiss-on-speed/>
- JoyTag: <https://github.com/fpgaminer/joytag> (photographic, uncensored, 5000+ tags)
- JoyCaption Beta One: <https://huggingface.co/fancyfeast/llama-joycaption-beta-one-hf-llava>
- WD EVA02-Large v3: <https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3>
- pi-workflow-engine: <https://github.com/timbrinded/pi-workflow-engine>
- Git-hooks comparison: <https://www.andymadge.com/2026/03/10/git-hooks-comparison/>
