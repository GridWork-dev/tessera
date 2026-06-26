# Product

## Register

product

## Users

A single power user — the owner of a large private local media library (~26,600 images + ~3,900 videos across 14 recurring subjects). Works in long, focused curation sessions, often in a dim room, on a dedicated Mac mini. Comfortable with pro tools (Lightroom, Bridge, Finder column view). Wants speed, density, and keyboard-driven flow — not hand-holding or consumer polish. Privacy is absolute: nothing about the library ever leaves the machine except inference calls.

## Product Purpose

A local-first **digital-asset manager** for tagging, searching, browsing, and curating the library. It surfaces a multi-tier ML pipeline (structured tags, SigLIP embeddings, captions, NudeNet metadata) as a fast, legible interface: filter by facets, run hybrid tag + semantic search, inspect per-asset metadata, and triage at scale. Success = the user can find any asset in seconds and curate hundreds per session without friction. The UI serves the workflow; it is never the spectacle.

## Brand Personality

Professional, dense, calm, restrained. Three words: **precise, quiet, fast.** A pro instrument — the chrome recedes so imagery and data dominate. No marketing voice, no celebration, no delight-for-its-own-sake. Confidence shown through responsiveness and information density, not ornament.

## Anti-references

- **SaaS dashboard templates** — cream/sand backgrounds, gradient accents, the hero-metric template (big number + small label + gradient), identical card grids.
- **Consumer photo apps** (Google Photos / Apple Photos) — oversized chrome, playful rounding, infinite-scroll-only browsing, hidden metadata.
- **Neon-on-dark / cyberpunk** — saturated cyan/purple gradients, glow, glassmorphism. The accent is one restrained jade, used as data not decoration.
- **Gradient text, side-stripe borders, tracked uppercase eyebrows on every section** — the saturated AI tells.

## Design Principles

1. **Density earns its keep.** Pack information where the user is scanning (grid, filmstrip, facet counts); decompress everything else for calm. Density is a tool, not a default.
2. **Chrome recedes, content dominates.** Cool dark surfaces and one accent so thumbnails and metadata are the brightest things on screen.
3. **Keyboard-first, mouse-optional.** A command bar (⌘K) and shortcuts are primary affordances, not extras. Every frequent action has a key.
4. **Every number is legible and honest.** Counts, ratings, confidences are real data rendered in mono — never decorative, never faked.
5. **Local-first, instant.** Virtualize everything; never block on the network. The tool should feel like a native app, not a web page.

## Accessibility & Inclusion

- WCAG **AA** minimum (body ≥4.5:1, large/UI ≥3:1) — verified against the Pigment ramp.
- **Dark-only** is a deliberate product decision (long sessions, dim room, imagery-forward), not a toggle. Documented, not an oversight.
- Body text ≥16px. Rating colors are reinforced by label/shape, never color alone (color-blind safe).
- `prefers-reduced-motion` honored on every transition (crossfade or instant fallback).
- Full keyboard operability; visible focus ring on every interactive element.
