---
title: First-run setup
description: The four-step first-run wizard — library, models, compute, and access — that gets your local library running.
group: Getting started
order: 30
---

On first launch, Tessera walks you through a four-step setup wizard. Each step is
a single one-time choice, and everything you configure stays on this machine.

## 1. Library

Choose the folder that holds your library. Tessera reads it in place — nothing is
moved, renamed, or uploaded. Image paths are stored relative to this folder, so
you can move the library later and re-point Tessera at it without breaking the
catalog.

## 2. Models

Model weights are pulled from Hugging Face on first run, not bundled in the
download. The wizard shows a size preview of exactly what will download — roughly
3.5 GB total — before anything is fetched.

One optional model is surfaced here: **NudeNet region detection** (AGPL-3.0). It
is off by default and produces region metadata only — it is never a content gate.
Leave it unchecked unless you want that metadata.

## 3. Compute

Tessera detects the best compute backend for your hardware and shows it
pre-selected:

- **Apple Silicon** — CoreML / MLX on the Neural Engine and GPU.
- **NVIDIA** — CUDA / TensorRT.
- **Windows GPU** — DirectML.
- **CPU only** — a slow fallback when no accelerator is available.

You can override the detected backend if you have a reason to. The default is the
fastest private path for your machine.

## 4. Access

By default Tessera binds to loopback (`127.0.0.1`), which is private to this
machine and needs no login. If you change the bind host to expose Tessera on your
network, the wizard requires you to create the first admin login — an open bind
without authentication is not allowed.

Bind host and port changes take effect after the server restarts.

When you finish, Tessera begins the initial index. Tagging, captions, and any
enabled lanes (faces, video scenes) are computed locally. Once the index is
running, you can start searching in plain language or browse by person, place, or
rating.

## Changing these later

Every choice here maps to a setting you can revisit. See
[Configuration](/docs/configuration) for the `config.yaml` and
`MEDIA_PIPELINE_*` environment-variable layout.
