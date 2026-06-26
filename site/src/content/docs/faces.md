---
title: Faces
description: Optional, off-by-default face recognition that groups people across your library, with GDPR/BIPA-aware opt-in and full erasure.
group: Organizing
order: 50
---

Tessera can recognize and group every appearance of a person across your whole
library. The feature is **off by default** and stays dark until you explicitly
opt in.

## Why it is opt-in

Face vectors are biometric data under GDPR Article 9 and laws like BIPA. Tessera
treats them accordingly: the entire faces lane is gated behind a single
`faces.enabled` switch that defaults to `false`. Nothing about who is in your
images is computed or stored until you turn it on.

When enabled, detection and embedding run entirely on-device — there is no cloud
face database and no network call. Face vectors are stored locally in a dedicated
face-vector store.

## Enabling it

Faces is enabled in your configuration:

```yaml
faces:
  enabled: false   # set to true to opt in — biometric data is opt-in
  detector: apple_vision
  embedder: sface   # Apache-2.0, 128-dim, commercial-safe default
```

You can also flip it for a single run with the `MP_FACES_ENABLED` environment
variable, without editing the config file. See
[Configuration](/docs/configuration) for the full block.

The default embedder is **SFace** (Apache-2.0) — commercial-safe and the
recommended choice. An alternative embedder is available for non-commercial use.

## How grouping works

Once enabled, Tessera detects faces, embeds each one, and clusters them into
people. Name a person once and Tessera surfaces every appearance of them across
the library. Clustering uses a chaining-resistant algorithm so well-separated
faces do not collapse into one mega-cluster.

## Right to erasure

Every person — and all of their face vectors — is fully erasable. Deleting a
person removes their biometric data from the store. Because nothing is uploaded,
local deletion is complete deletion; there is no server copy to chase.
