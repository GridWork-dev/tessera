---
title: Advanced faces
description: Swap the bundled SFace embedder for ArcFace to tighten clustering — an honest, download-it-yourself opt-in whose weights are non-commercial.
group: Organizing
order: 55
---

The bundled face embedder is **SFace** (Apache-2.0, 128-dim) — commercial-safe
and the recommended default. It is what ships, and for most libraries it is
enough. If you want tighter clusters and you are not using Tessera commercially,
you can swap in ArcFace.

This is an advanced, opt-in path. Read [Faces](/docs/faces) first — the entire
lane is off by default and stays dark until you enable it.

## ArcFace, and why it is not bundled

**ArcFace / buffalo_l** produces 512-dim embeddings and clusters faces more
cleanly than the 128-dim SFace default. The recognition code is permissively
licensed, but the published **weights are research / non-commercial only**.

So Tessera does not bundle them, and does not put them behind the Pro tier
either. Gating non-commercial weights behind a Pro feature would itself break
their license. ArcFace is a documented, download-it-yourself opt-in. You obtain
the weights, you accept their license, you point Tessera at them.

If you use Tessera for anything commercial, stay on SFace. The default exists for
exactly this reason.

## Switching to ArcFace

Download the `buffalo_l` ONNX weights yourself, place them at the configured
path, and select the embedder:

```yaml
faces:
  enabled: true
  embedder: arcface     # 512-dim, NON-COMMERCIAL weights — you supply them
  arcface_model_path: models/face/arcface_buffalo_l.onnx
  cluster_eps: 0.60     # ArcFace's 512-dim space wants a wider radius than SFace
```

If the weights file is missing, the faces lane reports the embedder as
unavailable and skips gracefully rather than failing — nothing is invented in its
place.

## Tune the clustering radius

`cluster_eps` is the cosine distance threshold the clusterer groups within. The
SFace default is `0.45`; ArcFace's 512-dim space separates differently, so use
`0.60`. Lower values split more aggressively (more, tighter people); higher
values merge more. Adjust to your library and re-cluster.

## Embedders never mix

Clustering partitions by embedder name, so 128-dim SFace vectors and 512-dim
ArcFace vectors are never compared against each other. This is a safety property,
not a limitation: a mixed store can never silently collapse two different
embedding spaces into one bad cluster.

The practical consequence: switching embedders means re-embedding and
re-clustering. Faces you already grouped under SFace will not merge with new
ArcFace faces — they live in separate spaces. Pick an embedder before you build
your people, or expect to rebuild them after the swap.
