---
title: Introduction
description: What Tessera is — a private, local-first AI digital-asset manager for your image and video library.
group: Getting started
order: 10
---

Tessera is a private, local-first digital-asset manager for a large image and
video library. It turns a folder of files into something you can search, browse,
and rediscover: structured tags, natural-language captions, semantic search,
faces, places, and video scenes — all computed and stored on your own machine.

## What it does

Tessera runs a multi-tier vision pipeline over everything you point it at:

- **Structured tags.** Every asset is described across categories — person,
  clothing, content type, pose, setting, lighting, mood, and free-form tags.
- **Captions.** A local vision-language model writes a natural-language caption
  per asset, giving you a browsable, filterable index from day one.
- **Semantic search.** Image embeddings let you search by meaning — "golden hour
  on the beach" — and find visually similar assets, not just filename matches.
- **Faces.** Optional, off by default. Group every appearance of a person, with
  vectors that never leave your disk.
- **Places and events.** Cluster by location and time into trips and moments.
- **Video scenes.** Clips are split into scenes with keyframe posters, so you can
  browse inside footage as easily as stills.

## What it is not

Tessera is not a cloud service. There is no account, no upload, and no telemetry.
Your assets, thumbnails, captions, faces, and embeddings are computed and stored
on your device. The only network traffic is the one-time model download on first
run, and any remote compute endpoint you explicitly configure yourself.

It is also not a content filter. Tessera organizes whatever you point it at,
privately, on your hardware. It does not inspect, restrict, or report your
library.

## How it is licensed

The complete local pipeline is open source under AGPLv3 — run it, audit it,
self-host it. Pro is a single one-time purchase that unlocks a small set of
software capabilities (bulk export, remote compute routing, priority support).
Pro never gates core features and never phones home. See
[Pro & licensing](/docs/licensing) for detail.

## Next steps

- [Install](/docs/install) — get the build for your platform.
- [First-run setup](/docs/first-run) — the four-step wizard.
- [Tagging & semantic search](/docs/tagging-search) — the core workflow.
