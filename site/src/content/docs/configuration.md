---
title: Configuration
description: Configure Tessera via config.yaml and MEDIA_PIPELINE_* environment variables, with a documented resolution precedence.
group: Reference
order: 90
---

Tessera reads its configuration from a layered set of sources. Most users never
touch a config file — the setup wizard writes what it needs — but every choice is
available to set directly.

## Resolution precedence

Settings are resolved lowest to highest, so a higher layer overrides a lower one:

1. **Shipped defaults** — portable defaults committed with the app.
2. **Per-user config** — `config.yaml` in your OS-appropriate config directory.
3. **Project `config.yaml`** — if present in the project root, read for
   back-compat.
4. **`MEDIA_PIPELINE_*` environment variables** — highest precedence.

Environment variables win over any file, which makes them the right tool for
per-run overrides and for keeping a machine-specific value out of a shared config
file.

## config.yaml

The config file is plain YAML. The blocks that matter for setup:

```yaml
library_root: "/path/to/your/library"

database:
  path: "data/catalog.db"
  journal_mode: "WAL"

webui:
  host: "127.0.0.1"   # loopback is private; a non-loopback bind requires auth
  port: 8000

compute:
  routes:
    embed: local_mps
    tag: local_mps
    caption: local_mps
    detect: local_mps

faces:
  enabled: false        # off by default — see the Faces guide
```

The compute seam is provider-agnostic: each capability (`embed`, `tag`,
`caption`, `detect`) is routed to a named backend, and backends are configured by
value. Swapping a backend is a config edit, not a code change.

## Environment variables

Every setting has a `MEDIA_PIPELINE_*` environment-variable form, using the field
path in upper snake case:

```bash
export MEDIA_PIPELINE_DATABASE_PATH=/data/catalog.db
export MEDIA_PIPELINE_WEBUI_PORT=8000
export MEDIA_PIPELINE_WEBUI_HOST=127.0.0.1
```

A few feature switches have their own variables:

- `MP_FACES_ENABLED` — opt into the faces lane for a single run without editing
  the config file.
- `MEDIA_PIPELINE_LICENSE` — supply a Pro license token by environment instead of
  a `license.key` file. See [Pro & licensing](/docs/licensing).

## Paths are portable

Image paths are stored relative to your library root, and the catalog and config
are plain files on disk. To move your install to another machine, copy the data
directory and re-point Tessera at your library — there is nothing machine-specific
baked into the catalog.

## Self-hosting the backend

If you run the backend as a service rather than the desktop app, bind it to your
private network (or a Tailscale address) rather than a public interface, and
enable authentication for any non-loopback bind. The source on
[GitHub](https://github.com/tessera-app/tessera) includes the service layout.
