# Tessera

**A local-first, private AI media library.** Organize, tag, caption, and search your own
photo & video library — entirely on your own machine.

[gettessera.xyz](https://gettessera.xyz) · [Documentation](https://gettessera.xyz/docs) · License: AGPL-3.0

Tessera enriches a personal media library with on-device AI — structured tags, semantic
embeddings, natural-language captions, faces, places, and deep-video understanding — then
gives you a fast, dense interface to search and curate it. Nothing leaves your machine. The
only optional external service is OpenRouter, and only if you opt into hosted inference.

Open-core: the full pipeline and app are free under the GNU AGPL-3.0. An optional one-time
**Pro** license unlocks a few convenience features; **no media and no core capability is ever
gated.**

## Features

- **Multi-tier enrichment** (all local):
  - Structured tags (JoyTag + WD EVA02-Large)
  - Semantic image embeddings → find-similar (SigLIP, sqlite-vec + an ANN index)
  - Natural-language captions (a vision-language model) with full-text caption search
  - NSFW region metadata (NudeNet) — metadata only, never a gate
- **Faces** — on-device detection + clustering, opt-in, never gated.
- **Places & Events** — geotag clustering into places and time-based events.
- **Deep video** — scene detection, scene thumbnails, and transcripts.
- **Personalized ranking** — a "more like this" probe learned from your keep/reject signals.
- **Fast UI** — a dense, justified grid with facets, an inspector, a command palette, and a
  docked lightbox (React 19, dark-only "Pigment" design system).
- **Runs where you do** — desktop app (Tauri) or self-hosted via Docker.

## Privacy

Tessera is built for sensitive personal libraries. Your files, paths, and metadata stay on
your machine. There is no telemetry and no cloud upload of your media. The only network call
the pipeline can make is to OpenRouter, and only if you opt into hosted inference.

## Tech

- **Backend** — Python 3.14, FastAPI, SQLAlchemy, SQLite (+ sqlite-vec) with an ANN vector index.
- **Frontend** — React 19, Vite, TanStack Router/Query, vanilla-extract, Biome.
- **Desktop** — Tauri 2.
- **Models** — JoyTag, WD EVA02-Large, SigLIP SO400M, a VLM captioner, NudeNet; runs on
  Apple Silicon (mlx) or CUDA.

## Getting started

See the [documentation](https://gettessera.xyz/docs) to install and configure, or the
[self-hosting guide](docs/packaging-self-host.md) to run the backend under Docker.

```bash
make dev      # backend (:8000) + frontend (:5173) dev servers
```

## License

Tessera's code is licensed under the **GNU AGPL-3.0** (see [LICENSE](LICENSE)). An optional
one-time Pro license is available at [gettessera.xyz](https://gettessera.xyz); it unlocks
convenience features only (advanced personalization, bring-your-own remote compute, priority
support). Every AI capability and all of your media remain fully usable under the open-source
license.

Contributions are welcome under the [Contributor License Agreement](CLA.md).
