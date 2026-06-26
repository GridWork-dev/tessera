---
title: FAQ
description: Common questions about privacy, models, faces, licensing, and moving your Tessera library between machines.
group: Reference
order: 120
---

## Is my library ever uploaded?

No. Indexing, search, faces, captions, and video scenes all run on your machine.
There is no telemetry and no account. The only network traffic is the one-time
model download and any remote compute endpoint you configure yourself.

## Do you inspect or restrict what is in my library?

No. It is your library. Tessera does not inspect, restrict, or report your
content — it organizes whatever you point it at, privately, on your hardware.

## How big are the models?

The first run downloads roughly 3.5 GB of local models from Hugging Face. After
that the app works fully offline. Plan for about 10 GB of free disk for the app
plus models.

## Why won't macOS let me open the app?

Until the first stable release is signed and notarized, Gatekeeper blocks unsigned
builds on a double-click. Right-click the app and choose **Open**, or use **System
Settings → Privacy & Security → Open Anyway**. You only need to do this once. See
[Install](/docs/install).

## Are faces on by default?

No. Face vectors are biometric data, so the faces lane is off by default and must
be explicitly enabled. Every person is fully erasable, and nothing leaves your
machine. See [Faces](/docs/faces).

## Is Pro a subscription?

No. Pro is a single one-time purchase, perpetual for the current major version.
There is no recurring charge.

## Does Pro phone home to check my license?

No. License validation is offline — an Ed25519 token verified on-device against a
baked-in public key. Pro works on an air-gapped machine. See
[Pro & licensing](/docs/licensing).

## What happens to my data if I stop paying?

Nothing. You buy Pro once; there is nothing to stop. Your library and app stay
exactly where they are.

## Can I move my library between machines?

Yes. The library and config are plain files, and image paths are stored relative
to your library root. Copy the data directory to a new machine and re-point
Tessera at your library. See [Configuration](/docs/configuration).

## Can I self-host the backend?

Yes. Run the backend as a service on your own box, bound to your private network
or a Tailscale address rather than a public interface, with authentication enabled
for any non-loopback bind. The source is on
[GitHub](https://github.com/tessera-app/tessera).

## Where do I get help?

Ask in [GitHub Discussions](https://github.com/tessera-app/tessera/discussions).
