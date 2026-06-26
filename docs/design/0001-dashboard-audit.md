# Dashboard Design Audit & Improvement Backlog (Lumen Edge)

> **Status:** Audit 2026-06-22 — overhaul in progress on branch `feat/ui-overhaul`
> **Scope:** The current Dashboard view. Design *tokens* are not the problem; *layout and
> information density* are.

## Context

The Lumen Edge token foundation is solid — dark palette, 4pt spacing scale, Inter +
JetBrains Mono, good motion. What's weak is how the Dashboard *uses* that foundation:
sparse layout, flat hierarchy, and stale data. This is a layout/density problem, not a
token problem.

## Problems

| # | Problem |
|---|---|
| 1 | **Wasted vertical space** — `space-y-16` between sections pushes KPIs far down a 1440p screen. |
| 2 | **Flat stat row** — 4 identical `grid-cols-4` cards with no hierarchy. "Images" should be the hero, not one of four equal siblings. |
| 3 | **Stale "Processing Pipeline" card** — shows `qwen2.5vl:7b-8k` and 6 images/min. WRONG: Phase 1 is done, DB has 26,590 rows, model stack moved to the M5 tiers. |
| 4 | **Underweight Quick Links** — plain `HorizonPanel` text tiles. Could be live preview thumbnails from `/media/thumb/:hash`. |
| 5 | **Wasted font load** — Space Grotesk is loaded but `.font-display` is unused in the Dashboard. |
| 6 | **No real-time feel** — stats fetched once on mount, never refreshed. |
| 7 | **Redundant footer** — echoes the KPI numbers already shown above. |

## Backlog (priority order)

### High value / low effort

| Item | Detail |
|---|---|
| Collapse vertical gaps | `space-y-16` → `8`, `py-12` → `8`. |
| Make the hero number sing | `text-4xl`/`5xl` with a muted subline (ref: Linear). |
| Live-refresh ticker | `setInterval` 5s while `remaining > 0`, pulsing dot. |
| Dynamic tier status | Replace the stale model card with Tier 0/1/2/3 status badges: queued / running / done / not configured. |

### Medium value / higher effort

| Item | Detail |
|---|---|
| Person cards | Real `/media/thumb` thumbnails as 80×80 avatars. |
| Tag distribution | Top-10 tag mini bar-chart — **lean: pure CSS, no Chart.js**. |
| Bento layout | Hero tile + flanking tiles + full-width progress (ref: Vercel). |

### Phase 2+ (after tagging runs)

| Item | Detail |
|---|---|
| Browse masonry grid | Density toggle (3 / 4 / 5 col). |
| Lightbox | Keyboard nav (J/K, F flag, R rate) + swipe. |
| Floating tag-filter sheet | Person chips, rating segmented control, tag multi-select with counts. Leverage the new `tags.tag_source` column for "JoyTag only" vs "VLM only" filter toggles. |

## One concrete CSS change

Remove **Space Grotesk** (flagged polarizing / experimental). Add **Instrument Serif**
(Google Fonts) for the hero numbers *only*, via a single `@import`. Keep **Inter** for
everything else. Distinctive with **zero component churn** — purely a font swap.

---

The lean overhaul (Dashboard + tooling) is being implemented on branch
**`feat/ui-overhaul`** with a **Playwright visual-audit harness**. Browse / Lightbox /
filters are deferred follow-ups.
