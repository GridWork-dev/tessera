#!/usr/bin/env bash
#
# Tier-2 caption sweep — loops `batch_tag.py --caption` until the scoped subset is
# drained, gating on the mlx Qwen2.5-VL :8081 /health endpoint. Designed to run
# under a launchd LaunchAgent with KeepAlive={Crashed:true} + RunAtLoad:
#   * clean drain  -> exit 0  -> launchd leaves it stopped (KeepAlive only on crash)
#   * server down  -> exit 1  -> launchd restarts later; RunAtLoad re-runs at boot
# The caption pass is idempotent (INSERT OR IGNORE on UNIQUE(image_id, model)),
# so a reboot or restart resumes cleanly via the captions resume select.
#
# Scope is the ~5k explicit+questionable subset by default (locked decision).
# Override with CAPTION_RATINGS="" to caption the whole corpus.

set -uo pipefail

ROOT="/Users/gw/media-pipeline"
cd "$ROOT" || exit 1

HEALTH_URL="http://127.0.0.1:8081/health"
BATCH="${CAPTION_BATCH:-200}"
RATINGS="${CAPTION_RATINGS-explicit,questionable}"
HEALTH_DEADLINE_SECS="${HEALTH_DEADLINE_SECS:-300}"  # 5-minute health poll

ratings_arg=()
[ -n "$RATINGS" ] && ratings_arg=(--ratings "$RATINGS")

echo "[caption_sweep] $(date '+%F %T') start — batch=$BATCH ratings='${RATINGS:-<all>}'"

# Wait for the mlx server to report healthy (up to HEALTH_DEADLINE_SECS).
deadline=$(( $(date +%s) + HEALTH_DEADLINE_SECS ))
until curl -sf -m 5 "$HEALTH_URL" 2>/dev/null | grep -q '"status":"healthy"'; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "[caption_sweep] mlx server not healthy after ${HEALTH_DEADLINE_SECS}s — exit 1 (launchd will retry)"
    exit 1
  fi
  echo "[caption_sweep] waiting for mlx :8081 health..."
  sleep 10
done

# Loop batches until a pass captions zero images (subset drained).
while true; do
  out=$(venv/bin/python batch_tag.py --caption --count "$BATCH" "${ratings_arg[@]}" 2>&1)
  echo "$out"
  n=$(printf '%s\n' "$out" | sed -nE 's/.*Captioned ([0-9]+) images.*/\1/p' | tail -1)
  if [ -z "$n" ]; then
    echo "[caption_sweep] could not parse caption count — exit 1 (launchd will retry)"
    exit 1
  fi
  if [ "$n" -eq 0 ]; then
    echo "[caption_sweep] $(date '+%F %T') drained — exit 0"
    exit 0
  fi
  echo "[caption_sweep] $(date '+%F %T') captioned $n this batch; continuing"
done
