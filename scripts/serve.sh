#!/usr/bin/env bash
# Persistent media-pipeline server, bound to the tailnet.
#
# Privacy: binds the Tailscale IPv4 only, so the private library is reachable
# over the tailnet and NOT the local LAN. If the tailnet IP is unavailable it
# FAILS CLOSED (refuses to start) rather than binding 0.0.0.0. For local-only dev
# use `make backend` (loopback bind from pipeline.settings) — this is the deploy
# path.
#
# launchd runs this in the foreground (KeepAlive) so it auto-starts on login and
# restarts on crash. See scripts/com.gridwork.media-pipeline.plist.
#
# Repo root is derived from this script's location ($0) — no hardcoded paths.
set -euo pipefail
cd "$(dirname "$0")/.."

# Box-local, NEVER-committed overrides (gitignored): on a trusted private tailnet
# a maintainer may set e.g. MEDIA_PIPELINE_AUTH_ENABLED=0 or MP_BIND_HOST here.
# The shipped default leaves auth to enforce on any non-localhost bind.
if [[ -f scripts/serve.local.env ]]; then
  set -a; . scripts/serve.local.env; set +a
fi

# Port: MP_PORT (legacy) or MEDIA_PIPELINE_WEBUI_PORT (settings env), else 8000.
PORT="${MP_PORT:-${MEDIA_PIPELINE_WEBUI_PORT:-8000}}"
TAILSCALE="${TAILSCALE_BIN:-/opt/homebrew/bin/tailscale}"

# Bind the tailnet IPv4 only. Fail CLOSED when it is unavailable — never silently
# fall back to 0.0.0.0 (that would expose the private library on every LAN
# interface). An operator can force a bind via MP_BIND_HOST (e.g. 127.0.0.1).
HOST="${MP_BIND_HOST:-$("${TAILSCALE}" ip -4 2>/dev/null | head -n1 || true)}"
if [[ -z "${HOST}" ]]; then
  echo "[serve] FATAL: tailscale IP unavailable and MP_BIND_HOST unset —" >&2
  echo "        refusing to bind 0.0.0.0. Set MP_BIND_HOST to bind deliberately." >&2
  exit 1
fi

echo "[serve] media-pipeline → http://${HOST}:${PORT}" >&2
exec ./venv/bin/python -m uvicorn webui.main:app --host "${HOST}" --port "${PORT}"
