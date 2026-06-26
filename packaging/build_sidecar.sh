#!/usr/bin/env bash
# Freeze the FastAPI sidecar (PyInstaller --onedir) and stage it where Tauri
# bundles it as a *resource*: src-tauri/binaries/mp-sidecar/ (launcher +
# _internal/). Run from the repo root (or anywhere — it cd's to the repo root).
#
# Why a resource, not externalBin: --onedir yields a DIRECTORY (launcher +
# _internal/ libs). Tauri externalBin ships a single file and can't carry
# _internal/, so we ship the whole dir as a `resource` (see tauri.conf.json
# `bundle.resources`) and the Rust shell execs the launcher next to its libs.
# The onedir choice is deliberate (onefile + torch = multi-minute cold start).
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-./venv/bin/python}"
NAME="mp-sidecar"
OUT="src-tauri/binaries"

echo "==> Freezing $NAME (--onedir)"
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES "$PY" -m PyInstaller packaging/sidecar.spec \
  --noconfirm --distpath packaging/dist --workpath packaging/build

mkdir -p "$OUT"
rm -rf "$OUT/$NAME"
cp -R "packaging/dist/$NAME" "$OUT/$NAME"
echo "==> Staged onedir payload at $OUT/$NAME (shipped as a Tauri resource)"
