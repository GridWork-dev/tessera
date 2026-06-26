"""Frozen-app entrypoint for the Tauri sidecar (Spec G).

Runs the existing FastAPI app (``webui.main:app``) under uvicorn on loopback.

- Sets the macOS **fork-after-Metal** safety env (the D-TEST-NATIVE-SEGV lesson)
  BEFORE any ML/Metal import, or the frozen app crashes the same way the test
  suite did once Metal initializes and something later forks.
- Free-port fallback so a second app instance can't wedge boot; the chosen port
  is printed on stdout (``MP_SIDECAR_PORT=<n>``) for the Tauri shell to read.
"""

from __future__ import annotations

import os
import socket
import sys


def _setup_env() -> None:
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def main() -> int:
    _setup_env()
    import uvicorn

    from webui.main import app

    port = _free_port(int(os.environ.get("MP_PORT", "8000")))
    print(f"MP_SIDECAR_PORT={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
