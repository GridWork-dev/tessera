---
title: Videos & scenes
description: Video as a first-class citizen — scene detection, keyframe posters, an in-app player, and per-video facets.
group: Organizing
order: 60
---

Video is a first-class citizen in Tessera, not an afterthought bolted onto an
image tool. Clips are indexed, split into scenes, and made searchable alongside
your stills.

## Scenes and posters

Each clip is split into scenes automatically. Tessera extracts a keyframe poster
per scene, so a long video becomes a row of legible thumbnails you can scan at a
glance instead of scrubbing.

## In-app player

Open a video to play it inline, with the timeline marked by scene chips. Jump
straight to a scene from its chip — the player and the scene index stay in sync.

## Per-video facets

Videos carry their own facets so you can filter footage the way you filter stills:

- **People** detected in the clip.
- **Duration** and **orientation**.
- **Audio** presence.

These combine with the same faceted search used for images, so a query can span
both media types.

## What runs locally

Scene detection, poster extraction, and the people lane all run on your machine
using the local pipeline and FFmpeg. As with everything in Tessera, your footage
is never uploaded.
