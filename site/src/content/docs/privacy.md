---
title: Privacy & local-first
description: Tessera collects nothing — no cloud, no telemetry, no account. Your library stays on your machine.
group: Reference
order: 100
---

Tessera is local-first by construction, not by policy. The short version: it
collects nothing. The longer version is below, and it is still short.

## Your library never leaves your machine

Tessera indexes, searches, and understands your images and video locally. Your
assets, thumbnails, captions, faces, and embeddings are computed and stored on
your own device. There is no server copy, and no way for anyone — including us —
to access them.

## No telemetry, no account

The app sends no analytics, crash reports, or usage pings. There is no account to
create and no login by default. After the one-time model download, Tessera runs
fully offline; you can use it on an air-gapped machine.

## The only network traffic

Two things, and both are explicit:

- **First-run model download.** Roughly 3.5 GB of local models are pulled from
  Hugging Face once. After that, nothing is required.
- **Bring-your-own remote compute.** Off by default. If you enable it, calls go to
  the endpoint *you* configure with *your* key — never to us. This is a Pro
  capability and the private, offline path is always available.

## No content inspection

Tessera does not inspect, restrict, or report your library. It organizes whatever
you point it at, privately, on your hardware. NudeNet region detection is optional
and produces metadata only — it is never a content gate.

## Faces are opt-in

Because face vectors are biometric data, the entire faces lane is off by default
and every person is fully erasable. See [Faces](/docs/faces) for the GDPR/BIPA
posture.

## Pro licensing is offline

A Pro license is verified on-device with no network call. Pro never phones home to
check your license, so it works on a fully offline machine. See
[Pro & licensing](/docs/licensing).
