#!/usr/bin/env bash
# =============================================================================
# h100_monitor.sh — live status of an in-flight run_h100_full.sh pass.
# Run from any terminal (it does NOT touch the run). Pass -f to follow the log.
#   bash scripts/h100_monitor.sh        # one snapshot
#   bash scripts/h100_monitor.sh -f     # follow /work/run.log live (Ctrl-c to stop)
# =============================================================================
set -uo pipefail
cd ~/media-pipeline
VASTAI=./venv/bin/vastai
BOX=outputs/h100/.box

if [ ! -f "$BOX" ]; then
  echo "No active run (outputs/h100/.box missing). Current Vast instances:"
  $VASTAI show instances 2>/dev/null | grep -vE 'DEPRECATED'
  exit 0
fi
# shellcheck disable=SC1090
source "$BOX"   # IID HOST PORT
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i ~/.ssh/id_ed25519 -p $PORT root@$HOST"

echo "=== instance $IID (status · GPU util · uptime · \$/hr) ==="
$VASTAI show instances 2>/dev/null | grep -vE 'DEPRECATED' | grep -E "ID|$IID" | head -3

if [ "${1:-}" = "-f" ]; then
  echo "=== following /work/run.log (Ctrl-c to stop) ==="
  exec $SSH 'tail -f /work/run.log'
fi

echo "=== GPU ==="
$SSH 'nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader' 2>/dev/null \
  | sed 's/^/  /' || echo "  (ssh unreachable — box may be booting or gone)"

echo "=== progress (last log lines: tierN done/26590 @ img/s) ==="
$SSH 'tail -4 /work/run.log 2>/dev/null; echo "  ---"; for f in tags captions nudenet; do printf "  %s.jsonl: %s\n" "$f" "$(wc -l < /work/out/$f.jsonl 2>/dev/null || echo 0)"; done; test -f /work/full.done && echo "  >>> RUN COMPLETE (full.done)" || echo "  >>> still running"' 2>/dev/null \
  | sed 's/^/  /'
echo
echo "tip: follow live with  bash scripts/h100_monitor.sh -f   |   or reattach the driver: tmux attach -t h100"
