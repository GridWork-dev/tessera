#!/usr/bin/env python3
"""Issue an Ed25519-signed offline license token (ISSUER side).

The private signing key NEVER lives in the repo or the app. This tool reads it
from (in precedence order):

  1. ``--private-key-file <path>``     (raw base64, one line)
  2. ``MEDIA_PIPELINE_LICENSE_PRIVATE_KEY`` env var (raw base64)

and emits the signed ``MPL-<TIER>-<OPAQUE>`` token to stdout. The app verifies it
offline against the baked-in public key in ``pipeline/license_tokens.py``.

Examples
--------
Generate a keypair (private stays secret; bake the public into the app)::

    python scripts/issue_license.py --gen-key

Issue a perpetual v1 Pro token for a customer::

    MEDIA_PIPELINE_LICENSE_PRIVATE_KEY=<b64> \\
        python scripts/issue_license.py --tier pro --max-version 1 \\
        --customer cust_123

Issue a token that expires (annual-updates style; perpetual fallback handled by
the app's max_version check)::

    python scripts/issue_license.py --tier pro --max-version 2 \\
        --private-key-file ./issuer.key --expires-days 365
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running as a plain script (``python scripts/issue_license.py``).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.license_tokens import (  # noqa: E402
    LicenseClaims,
    generate_keypair,
    load_private_key_b64,
    sign_token,
)

PRIVATE_KEY_ENV = "MEDIA_PIPELINE_LICENSE_PRIVATE_KEY"


def _resolve_private_key_b64(args: argparse.Namespace) -> str:
    if args.private_key_file:
        path = Path(args.private_key_file).expanduser()
        if not path.is_file():
            sys.exit(f"error: private key file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    env = os.environ.get(PRIVATE_KEY_ENV)
    if env:
        return env.strip()
    sys.exit(
        "error: no private key. Pass --private-key-file or set "
        f"{PRIVATE_KEY_ENV}. (Generate one with --gen-key.)"
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Issue an Ed25519-signed offline license token."
    )
    p.add_argument(
        "--gen-key",
        action="store_true",
        help="generate a fresh Ed25519 keypair and exit (private + public b64)",
    )
    p.add_argument("--tier", default="pro", help="license tier (default: pro)")
    p.add_argument(
        "--max-version",
        type=int,
        default=1,
        help="highest app MAJOR version this license grants Pro on (perpetual-per-major)",
    )
    p.add_argument("--customer", default=None, help="optional opaque customer id")
    p.add_argument(
        "--expires-days",
        type=int,
        default=None,
        help="optional expiry, N days from now (omit for perpetual)",
    )
    p.add_argument(
        "--private-key-file",
        default=None,
        help=f"raw base64 private key file (else read {PRIVATE_KEY_ENV})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.gen_key:
        priv_b64, pub_b64 = generate_keypair()
        print("# Ed25519 keypair (raw, base64). KEEP THE PRIVATE KEY SECRET.")
        print(f"PRIVATE (issuer only): {priv_b64}")
        print("PUBLIC  (bake into pipeline/license_tokens.py PUBLIC_KEY_B64):")
        print(pub_b64)
        return 0

    private_key = load_private_key_b64(_resolve_private_key_b64(args))
    now = int(time.time())
    expires = now + args.expires_days * 86400 if args.expires_days is not None else None
    claims = LicenseClaims(
        tier=args.tier,
        max_version=args.max_version,
        issued_at=now,
        customer_id=args.customer,
        expires=expires,
    )
    print(sign_token(claims, private_key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
