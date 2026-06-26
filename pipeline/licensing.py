"""
Pro-license gating — Ed25519-signed offline tokens (Immich pattern).

Sells SOFTWARE, not content. There is **no content gate** anywhere in this
module — uncensored capability is the product's wedge and stays free. What a Pro
license unlocks is a small set of *software capabilities* (feature flags), the
same dual-license model Immich / ente / PhotoPrism use on top of AGPLv3.

Offline by default: the license token is read from the ``MEDIA_PIPELINE_LICENSE``
environment variable or a ``license.key`` file in the project root. NO phone-home,
no network call. An empty / unknown / malformed / **forged** / expired /
over-version token fails safe to the ``community`` tier (all core features remain
available).

Verification is **real** now (was a forgeable shape-check): the token's
``<OPAQUE>`` segment carries a signed claims payload that is checked against a
baked-in Ed25519 **public** key (``pipeline.license_tokens.PUBLIC_KEY_B64``). The
**private** signing key lives only in the issuer (``scripts/issue_license.py``),
never in the app.

Pricing = one-time **perpetual, per MAJOR version**: a token grants Pro iff it
verifies AND its signed ``max_version`` claim is ``>=`` the running app's current
major version (``APP_MAJOR_VERSION``). A v1 license keeps working on every v1.x but
drops to community on v2 — never bricks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pipeline.license_tokens import LicenseClaims, verify_token

ENV_VAR = "MEDIA_PIPELINE_LICENSE"
KEY_FILENAME = "license.key"

# The running app's MAJOR version. A token grants Pro only while its signed
# ``max_version`` claim is >= this. Bump on each paid major; free within a major.
APP_MAJOR_VERSION = 1


class Tier(str, Enum):
    """License tier. ``community`` is the free AGPL build; ``pro`` is paid."""

    COMMUNITY = "community"
    PRO = "pro"


class ProFeature(str, Enum):
    """Software capabilities a Pro license unlocks. NEVER a content gate."""

    BULK_EXPORT = "bulk_export"
    REMOTE_COMPUTE_ROUTING = "remote_compute_routing"
    PRIORITY_SUPPORT = "priority_support"


# Features available without a Pro license. Everything not listed here as
# pro-only is community (the core DAM + all tiers + uncensored capability).
PRO_ONLY: frozenset[ProFeature] = frozenset(
    {
        ProFeature.BULK_EXPORT,
        ProFeature.REMOTE_COMPUTE_ROUTING,
        ProFeature.PRIORITY_SUPPORT,
    }
)


@dataclass(frozen=True)
class LicenseStatus:
    """The resolved license state for this install."""

    tier: Tier = Tier.COMMUNITY
    features: frozenset[ProFeature] = field(default_factory=frozenset)
    detail: str = "no license token; community tier"

    def has(self, feature: ProFeature) -> bool:
        return feature in self.features


def _read_token(project_root: Path | None = None) -> str | None:
    """Read the license token from env, then a ``license.key`` file. Offline."""
    token = os.environ.get(ENV_VAR)
    if token:
        return token.strip()
    root = project_root or Path(__file__).resolve().parent.parent
    key_file = root / KEY_FILENAME
    if key_file.is_file():
        try:
            content = key_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return content or None
    return None


def _claims_grant_pro(claims: LicenseClaims | None) -> bool:
    """A verified claim grants Pro iff tier==pro AND max_version covers this major.

    The signature + expiry were already checked by ``verify_token``; this applies
    the perpetual-per-major rule. Over-version (``max_version < APP_MAJOR_VERSION``)
    downgrades to community — never bricks.
    """
    if claims is None:
        return False
    if claims.tier.lower() != Tier.PRO.value:
        return False
    return claims.max_version >= APP_MAJOR_VERSION


def verify_pro(token: str | None) -> bool:
    """Does ``token`` cryptographically grant Pro for the running major version?

    Real Ed25519 verification + perpetual-per-major check. Fail safe to ``False``
    for unknown / malformed / forged / tampered / expired / over-version tokens.
    """
    return _claims_grant_pro(verify_token(token))


def parse_token(token: str | None) -> Tier:
    """Verify token signature + max_version -> tier. Fail safe to community.

    Back-compat shim around :func:`verify_pro`: the historical public API returns
    a :class:`Tier`. Only a token whose **signed** payload verifies against the
    baked-in public key, claims ``tier == "pro"``, is not expired, and whose
    ``max_version >= APP_MAJOR_VERSION`` yields :attr:`Tier.PRO`. Everything else
    (forged / malformed / over-version / expired) yields :attr:`Tier.COMMUNITY`.
    """
    return Tier.PRO if verify_pro(token) else Tier.COMMUNITY


def load_license(project_root: Path | None = None) -> LicenseStatus:
    """Resolve the current license status (offline). Never raises."""
    token = _read_token(project_root)
    claims = verify_token(token)
    if _claims_grant_pro(claims):
        return LicenseStatus(
            tier=Tier.PRO,
            features=frozenset(PRO_ONLY),
            detail="valid pro token (signature + max_version verified)",
        )
    detail = "no valid pro token; community tier"
    if token and claims is None:
        detail = "token failed verification; community tier (fail safe)"
    elif claims is not None and claims.max_version < APP_MAJOR_VERSION:
        detail = (
            f"token max_version {claims.max_version} < app major "
            f"{APP_MAJOR_VERSION}; community tier"
        )
    return LicenseStatus(tier=Tier.COMMUNITY, features=frozenset(), detail=detail)


def feature_enabled(
    feature: ProFeature, *, status: LicenseStatus | None = None
) -> bool:
    """Is ``feature`` available under the current (or supplied) license?

    Community-tier features (anything not in ``PRO_ONLY``) are always enabled.
    Pro-only features require an active pro license.
    """
    if feature not in PRO_ONLY:
        return True
    st = status or load_license()
    return st.has(feature)


__all__ = [
    "APP_MAJOR_VERSION",
    "ENV_VAR",
    "KEY_FILENAME",
    "PRO_ONLY",
    "LicenseStatus",
    "ProFeature",
    "Tier",
    "feature_enabled",
    "load_license",
    "parse_token",
    "verify_pro",
]
