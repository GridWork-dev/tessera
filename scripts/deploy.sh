#!/usr/bin/env bash
# Clean deploy: rebuild the frontend bundle, then (re)install + (re)start the
# persistent tailnet server as a launchd LaunchAgent. Idempotent — run any time
# after changes. The server then survives logout/reboot and restarts on crash.
#
# Local dev is unaffected: `make backend` still serves 127.0.0.1:8000.
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.gridwork.media-pipeline"
SRC_PLIST="scripts/${LABEL}.plist"
DEST_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"
TAILSCALE="${TAILSCALE_BIN:-/opt/homebrew/bin/tailscale}"

echo "==> [1/4] Building frontend (tsc -b && vite → frontend/dist)…"
( cd frontend && npm run build )

echo "==> [2/4] Stopping any ad-hoc dev server on :8000 (nohup python -m webui.main)…"
pkill -f "webui.main" 2>/dev/null || true

echo "==> [3/4] Installing LaunchAgent → ${DEST_PLIST}"
mkdir -p "${HOME}/Library/LaunchAgents" outputs
# Render the box-agnostic plist template: launchd needs absolute paths, so
# substitute the repo root (this script already cd'd to it) at install time.
REPO_ROOT="$(pwd)"
sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "${SRC_PLIST}" > "${DEST_PLIST}"
# bootout is async; bootstrapping too soon races with "I/O error 5". Wait for the
# domain to settle, then bootstrap with one retry, and always kickstart so the
# process restarts with the freshly built code.
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
sleep 1
launchctl bootstrap "${DOMAIN}" "${DEST_PLIST}" 2>/dev/null \
  || { sleep 2; launchctl bootstrap "${DOMAIN}" "${DEST_PLIST}" 2>/dev/null || true; }
launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null || true

echo "==> [4/4] Waiting for health…"
# Health-check against the same host serve.sh binds (tailnet IP, or an explicit
# MP_BIND_HOST). No 0.0.0.0 fallback — serve.sh fails closed without a tailnet IP.
HOST="${MP_BIND_HOST:-$("${TAILSCALE}" ip -4 2>/dev/null | head -n1 || true)}"
ok=""
for _ in $(seq 1 20); do
  if curl -fsS "http://${HOST}:8000/api/stats" >/dev/null 2>&1; then ok=1; break; fi
  sleep 0.5
done

if [[ -n "${ok}" ]]; then
  echo "==> Deployed ✓  Serving on http://${HOST}:8000 (tailnet)"
else
  echo "==> Service installed but health check did not pass yet." >&2
  echo "    Check: tail -f outputs/server.log" >&2
  exit 1
fi
