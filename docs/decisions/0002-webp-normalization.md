# ADR-0002: Image Normalization to WebP Q=90

> **Status:** ACCEPTED 2026-06-22 (Phase 1 complete)
> **Scope:** Destructive corpus-wide re-encode of all cataloged images to a single
> uniform format. Pairs with the destructive rename/relative-path work (commit `47be62e`).

## Context

The catalog needed one uniform image format so Tier 0/1 batch inference reads a single
decode path across all 26K images. The corpus was **~93% already-lossy JPEG**, so the
question was not "lossy vs lossless" — that ship had sailed at ingest — but which target
format minimizes friction for repeated full-corpus inference passes.

A JPEG→WebP re-encode at Q=90 is therefore **one generation of re-encode on
already-lossy sources**, visually imperceptible (SSIM > 0.98). We are not destroying
pristine masters; there are almost none to destroy.

## Decision: WebP Q=90 via pyvips, uniform corpus

Normalize every cataloged image to WebP Q=90 using the pyvips path. Accept the
`--force` corpus-wide re-encode to guarantee **format uniformity** over minimum bytes.

### Why WebP, not JXL or AVIF

JXL and AVIF both beat WebP on raw compression ratio. Both are **disqualified for this
stack** on decode, not encode:

| Format | Compression | Disqualifier |
|---|---|---|
| **WebP** | baseline | ✅ pyvips path fast, universally decodable |
| **JXL** | better | ❌ Pillow JXL decode is version-gated / not guaranteed present |
| **AVIF** | best | ❌ AV1 decode is measurably the slowest — bottlenecks the dataloader across 26K-image Tier 0/1 passes |

For a workload defined by *repeated full-corpus decode*, decode speed and universal
availability dominate. WebP wins on both.

### Why `--force` (uniformity over bytes)

The `--force` re-encode bypass was **intentional and deliberate**. Corpus uniformity —
every file the same format, same decode path — is worth more than minimum file size when
the corpus is read end-to-end on every inference pass. This is a one-time corpus-wide
action, not the default ingest behavior.

## Caveats

### CAVEAT 1 — re-encoding .webp → .webp can GROW files

A `.webp` → `.webp` round-trip grew the test file by **+9.8%**. This is expected (WebP is
already compressed; re-encoding adds a generation without removing redundancy). The
scanner **correctly SKIPS existing `.webp` by default**, so routine future ingests are
safe and never re-grow. The corpus-wide `--force` re-encode was the single deliberate
exception, accepted with eyes open.

### CAVEAT 2 — provenance side effect of pixel-identical dedup

The normalize collapsed a set of pixel-identical near-duplicates via **last-write-wins on
the WebP hash**. Two framings, both correct — cite both; exact counts live in the
normalize logs / the project guidelines:

- **1,772** pixel-identical collapses (per the project guidelines).
- The dedup grouped these into **~1,519** near-duplicate groups.

This is correct dedup behavior, but it was a **side effect** of identical pixels encoding
to identical bytes — not the intended primary path. The dedup happened *because* the
encode was deterministic, not *in order to* dedup.

**RECOMMENDATION:** if provenance auditing is ever needed, log which source hashes were
collapsed into which survivor. Today that mapping is not retained beyond the normalize logs.

## Result state

| Metric | Value |
|---|---|
| Cataloged images | 26,590 |
| WebP | 26,588 |
| GIF | 2 |
| Paths | all relative, **0 absolute** |
| Bad dims | **0** |
