# ADR-0003: Video Normalization & Keyframe Ingestion (Phase 4)

> **Status:** PROPOSED — deferred to Phase 4
> **Scope:** The 3,931 videos currently sitting in `content/library/` with **0 rows** in
> the catalog DB. Locks the shape now; execution waits until tiers can consume them.

## Context

The library holds **3,931 videos (~343–358 GB on disk)**, intermixed under
`content/library/` alongside images but **entirely absent from the catalog** — zero rows.
That is roughly **18× the image footprint** in bytes for ~15% of the file count.

Despite the size, there is no reason to ingest them yet.

## Why DEFERRED

| Reason | Detail |
|---|---|
| Not ingested | `SUPPORTED_EXTENSIONS` excludes video extensions — the scanner never sees them. |
| Tiers are image-only | Tier 0 (taggers) and Tier 1 (embedder) take stills, not video. |
| No consumer | Nothing downstream queries or displays video. |

There is **no value** in normalizing or cataloging videos until the tag/search index can
actually consume them. Deferring avoids 343+ GB of transcode churn for a feature with no
reader.

## Decision (proposed for Phase 4)

### Encoder

- **ffmpeg** with **Apple Silicon hardware encode** — `h264_videotoolbox` /
  `hevc_videotoolbox` — ~**100 fps** encode vs **<10 fps** software. Hardware is the only
  sane path at this corpus size.

### Container

- **mp4 / yuv420p** for universal decode.

### Key design: keyframe extraction, not monolithic blobs

The pivotal design choice: per-shot **keyframe extraction** produces representative
stills that feed **directly into the existing Tier 0/1 tagger + embedder**. Videos enter
the tag/search index **via their keyframes**, NOT as opaque video blobs. This reuses the
entire image pipeline unchanged — keyframes are just images.

### Phase 4 execution order

1. `ffprobe` → metadata (duration, codec, dims, shot boundaries).
2. Keyframe extraction → representative per-shot stills.
3. Feed keyframes through **Tier 0/1** (tagger + embedder) → index coverage.
4. Transcode for storage (`*_videotoolbox` → mp4/yuv420p).

Indexing precedes storage transcode: search coverage is the goal, the storage re-encode
is housekeeping.
