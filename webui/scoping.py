"""Per-user row scoping for media reads (audit C1 / multi-user).

Every media table (images, videos, scenes, …) carries a nullable ``owner_id``
(migration 012). A NULL owner means "un-owned / legacy" — visible to everyone.
This module centralizes the single visibility rule so list / detail / search
paths stay consistent:

  * auth OFF, or no authenticated principal, or an ADMIN principal  -> see ALL
    rows (``viewer_owner_id`` resolves to None -> scoping is a no-op).
  * a non-admin principal                                          -> see own
    rows (``owner_id == user_id``) PLUS legacy un-owned rows
    (``owner_id IS NULL``).

DORMANT on a single-user / auth-off deployment: ``viewer_owner_id`` resolves to
None there, so every query is returned unchanged and behavior is identical to
before. The rule only activates once auth is enabled AND a non-admin user is
logged in — i.e. real multi-user. Destructive routes are already locked to
admins via ``webui.auth_routes.require_admin``; this adds the read side.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_


def viewer_owner_id(request: Any) -> int | None:
    """The user_id a caller's reads are scoped to, or None for "see everything".

    None when there is no request, no authenticated principal, or the principal
    is an admin. Otherwise the non-admin principal's ``user_id``.
    """
    if request is None:
        return None
    principal = getattr(getattr(request, "state", None), "principal", None)
    if principal is None or getattr(principal, "is_admin", False):
        return None
    return getattr(principal, "user_id", None)


def scope_query(query, model, request):
    """Apply owner scoping to a SQLAlchemy ``query`` over ``model``.

    No-op when the viewer is unscoped (admin / auth-off). Otherwise narrows to
    the viewer's own rows plus legacy un-owned (NULL) rows. ``model`` must
    expose an ``owner_id`` column.
    """
    uid = viewer_owner_id(request)
    if uid is None:
        return query
    return query.filter(or_(model.owner_id == uid, model.owner_id.is_(None)))


def scope_by_owner_via(query, link_col, request):
    """Scope an aggregate over a child table (tags / captions / embeddings) to
    the viewer by joining its owning ``Image`` via ``link_col`` (the child's
    ``image_id`` column) and filtering ``Image.owner_id``.

    No-op when the viewer is unscoped (admin / auth-off): returns ``query``
    unchanged with NO join added, so the existing aggregate fast-path and its
    counts are byte-for-byte identical to before owner-scoping existed. The join
    + owner filter only appear for a scoped non-admin viewer. ``link_col`` is the
    child table's FK column to ``Image.id`` (e.g. ``Tag.image_id``).
    """
    uid = viewer_owner_id(request)
    if uid is None:
        return query
    from pipeline.database import Image

    return query.join(Image, link_col == Image.id).filter(
        or_(Image.owner_id == uid, Image.owner_id.is_(None))
    )


def can_view(row: Any, request: Any) -> bool:
    """Object-level visibility check for single-row (detail) fetches.

    True when unscoped (admin / auth-off), or the row is un-owned, or the row is
    owned by the viewer — used to turn a cross-tenant fetch into a 404.
    """
    uid = viewer_owner_id(request)
    if uid is None:
        return True
    owner = getattr(row, "owner_id", None)
    return owner is None or owner == uid
