---
title: Pro & licensing
description: The open-core model — AGPLv3 core always free, a one-time Pro purchase verified offline with Ed25519, no subscription, no phone-home.
group: Reference
order: 110
---

Tessera is open core. The complete local pipeline is free and open source under
AGPLv3. Pro is a single one-time purchase that unlocks a small set of software
capabilities. Pro sells software, never content — the uncensored core stays free.

## What Free includes

The Free edition (AGPLv3) is the full local pipeline:

- Semantic search and visual similarity
- Auto-tagging and captions
- Faces, places, and video scenes
- 100% local, no telemetry
- Self-hostable

You can run it, audit it, and self-host it with no license at all.

## What Pro unlocks

Pro adds software capabilities, not content access:

- **Advanced personalization** — ranking that adapts harder to your keep / reject signal.
- **Bring-your-own remote compute key** — point heavy jobs at your own remote compute.
- **Priority email support** — direct email, 2–3 business days.

Nothing in Pro gates a core capability. A missing or invalid license fails safe to
the Free tier, with every core feature intact.

## Pricing model

Pro is a single one-time purchase — there is no subscription and no recurring
charge. The license is **perpetual per major version**: your purchase unlocks Pro
for the current major version forever. A future major version is a separate,
optional one-time purchase, and your installed version keeps working regardless. A
newer major shows a gentle prompt, never a hard lockout.

## Offline verification

License validation is fully offline. A Pro token is an Ed25519-signed claims
payload, verified on-device against a public key baked into the app. The private
signing key lives only with the issuer, never in the build.

Tessera never calls a server to verify your license, so Pro works on an
air-gapped machine. The token is read from the `MEDIA_PIPELINE_LICENSE`
environment variable or a `license.key` file in the project root.

An empty, unknown, malformed, forged, expired, or over-version token fails safe to
the Free tier — it never bricks. An over-version token (one whose signed
`max_version` is below the running major) simply downgrades to Free.

## If you stop paying

There is nothing to stop. You buy Pro once. Your library and your app stay exactly
where they are, on your machine, with no expiry.
