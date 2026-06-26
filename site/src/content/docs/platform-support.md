---
title: Platform support
description: What runs today on macOS, Windows, and Linux, the current unsigned-build status, and system requirements — honest about tested versus in progress.
group: Getting started
order: 25
---

Tessera is developed and tested primarily on **macOS (Apple Silicon)**. The
indexing pillars run cross-platform, but Windows and Linux are still being
brought to first-class parity. This page is honest about what works today.

## Status by feature

| Capability | macOS | Windows / Linux |
| --- | --- | --- |
| Tags, embeddings, search, NudeNet | works | works |
| Captions (Tier 2 VLM) | works (mlx) | swap the caption route to a local server |
| Faces — embedding & clustering | works | works |
| Faces — detector | works (Apple Vision) | in progress (cross-platform detector) |
| Video ingest | works | needs `ffmpeg` / `ffprobe` on `PATH` |
| Desktop bundle | works | in progress (per-OS build matrix) |

Tags, embeddings, search, and NudeNet metadata work on all three platforms today
through ONNX Runtime's execution-provider probing — see
[Compute providers](/docs/providers).

The remaining gaps are honest ones. Tier 2 captions use mlx, which is
macOS-only; on Windows and Linux you point the caption route at any
OpenAI-compatible local server. Face detection currently uses Apple Vision, so
the on-Windows/Linux detector is still in progress; face embedding and clustering
already work everywhere. Video ingest needs `ffmpeg` available on the path.

If you run from source rather than a desktop bundle, the indexing pillars work on
all three platforms now.

## Signing status

Builds are currently **unsigned**. This is expected until the first stable
release; it is not a sign of compromise. Every release publishes SHA-256
checksums — verify your download before running it.

On macOS, Gatekeeper will refuse to open an unsigned build on a double-click. Use
the right-click **Open** path (or **System Settings → Privacy & Security → Open
Anyway**), documented step by step under [Install](/docs/install#macos). On
Windows, SmartScreen may warn that the publisher is unrecognized; choose
**More info → Run anyway**.

Code signing and notarization (Apple Developer ID on macOS) are planned, after
which these steps go away.

## System requirements

| Platform | Minimum |
| --- | --- |
| macOS | 13 Ventura or newer, Apple silicon or Intel |
| Windows | 10 / 11, 64-bit (DirectX 12 GPU recommended) |
| Linux | x86_64, glibc 2.31 or newer |

All platforms: 8 GB RAM (16 GB recommended) and roughly 10 GB of free disk for
the app plus models. The first launch downloads about 3.5 GB of local models;
after that Tessera runs fully offline. The catalog and thumbnail cache grow with
your library.
