"""CLI: ``python -m pipeline.weights status|plan|pull [--include-nudenet]``.

A thin wrapper over ``pipeline.weights.delivery`` for first-run setup and CI.
``--include-nudenet`` is the explicit AGPL opt-in; without it NudeNet is never
touched. ``--only KEY [KEY ...]`` restricts pull/plan to specific models.
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline.weights import delivery


def _fmt_gb(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m pipeline.weights", description="Model-weights delivery"
    )
    ap.add_argument("command", choices=("status", "plan", "pull"))
    ap.add_argument(
        "--include-nudenet", action="store_true", help="opt into the AGPL NudeNet pull"
    )
    ap.add_argument("--no-optional", action="store_true", help="required models only")
    ap.add_argument(
        "--only", nargs="+", metavar="KEY", help="restrict to specific manifest keys"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    opt_in = args.include_nudenet
    include_optional = not args.no_optional

    if args.command == "status":
        out = delivery.status(include_opt_in=opt_in)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"models root: {out['models_root']}")
            print(
                f"offline ready: {out['offline_ready']} ({out['required_missing']} required missing)"
            )
            for m in out["models"]:
                mark = {True: "✓", False: "·", None: "?"}[m["present"]]
                req = "required" if m["required"] else "optional"
                print(
                    f"  {mark} {m['key']:<14} {req:<9} {_fmt_gb(m['approx_size_mb']):>8}  {m['title']}"
                )
        return 0

    if args.command == "plan":
        out = delivery.plan(include_optional=include_optional, include_opt_in=opt_in)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(
                f"would pull {out['count']} model(s), ~{_fmt_gb(out['approx_total_mb'])}:"
            )
            for m in out["to_pull"]:
                print(
                    f"  - {m['key']:<14} {_fmt_gb(m['approx_size_mb']):>8}  ({m['source']}) {m['title']}"
                )
            if out["already_present"]:
                print(f"already present: {', '.join(out['already_present'])}")
        return 0

    # pull
    out = delivery.pull(
        include_optional=include_optional, include_opt_in=opt_in, only=args.only
    )
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for r in out["results"]:
            print(f"  [{r['status']}] {r['key']}: {r['message']}")
        print(
            f"pulled={len(out['pulled'])} present={len(out['present'])} errors={len(out['errors'])}"
        )
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
