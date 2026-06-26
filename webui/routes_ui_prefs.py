"""UI-preferences API — GET/PUT the versioned prefs blob.

NOT named routes_preferences.py: avoids clashing with the existing
active-learning routes_preference.py. Persists via pipeline.ui_prefs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pipeline import ui_prefs

router = APIRouter(prefix="/api/ui-prefs", tags=["ui-prefs"])


class PrefsBody(BaseModel):
    version: int = 1
    ui: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def get_prefs() -> dict[str, Any]:
    return ui_prefs.load_prefs()


@router.put("")
def put_prefs(body: PrefsBody) -> dict[str, Any]:
    return ui_prefs.save_prefs(body.model_dump())
