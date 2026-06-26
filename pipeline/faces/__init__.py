"""Faces lane — off-by-default, opt-in, right-to-erasure face recognition.

Detection (Apple Vision, on-device ANE) + a pluggable, commercial-safe-by-default
embedder (SFace ONNX, 128-dim, Apache-2.0) + incremental DBSCAN clustering over a
dedicated face-vector store (migration 009: ``people`` + ``faces``).

PRIVACY: face vectors are GDPR Art.9 / BIPA biometric data. The whole feature is
gated behind ``faces.enabled`` (default ``False``) and every person — with their
face vectors — is fully erasable. Nothing here makes a network call; detection
and embedding run on-box only.
"""

from __future__ import annotations

from pipeline.faces.config import faces_config, faces_enabled

__all__ = ["faces_config", "faces_enabled"]
