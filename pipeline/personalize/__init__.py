"""
Personalization rungs 1-2 over the stored SigLIP vectors.

- ``probe``: few-shot linear probe (numpy logistic regression) — rung 1.
- ``active_learning``: uncertainty ranking over the keep/reject flag signal —
  rung 2.
- ``api``: ``build_router(db)`` FastAPI factory.

Rungs 3-4 (LoRA fine-tunes) are explicitly OUT of scope (GPU-dependent, later).
numpy-only, no model load, no GPU. The probe is a NEW module and does NOT edit
``pipeline/centroid_tagger.py`` — it imports that module's stable read helpers.
"""

from __future__ import annotations

from pipeline.personalize import active_learning, probe

__all__ = ["active_learning", "probe"]
