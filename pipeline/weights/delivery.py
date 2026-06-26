"""First-run weight delivery — status / plan / pull over the manifest (Spec E).

Pulls model weights on first run instead of bundling them. The files-based ONNX
taggers land under ``settings.models_cache_dir`` (``models/`` by default) in the
``<dest>/`` dirs the inference loaders read (``pipeline.tier0_tagger`` /
``pipeline.compute.local_onnx_base`` resolve the same root). HuggingFace repos go
to huggingface_hub's OWN cache (``hf_cache_dir()`` → ``HF_HUB_CACHE`` / ``HF_HOME``),
the same place ``transformers.from_pretrained`` reads — so pull and runtime agree
without the app exporting anything.

Design points the wizard relies on:

* ``status()`` — per-model present/absent + an ``offline_ready`` flag (are all
  required models on disk? then first-run network is no longer needed).
* ``plan()`` — dry-run size preview of what a pull WOULD fetch (no network).
* ``pull()`` — resumable download of what's missing. HF downloads resume natively;
  a gated/auth failure degrades to a friendly per-model error instead of crashing
  the run. NudeNet (AGPL) is only ever touched when ``include_opt_in`` is set.

``huggingface_hub`` is imported lazily inside the functions that need it, so
importing this module is cheap and tests can monkeypatch the download calls.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from pipeline.settings import get_settings
from pipeline.weights.manifest import ModelSpec, selected, total_size_mb


def models_root() -> Path:
    """Root dir for the files-based weights (``settings.models_cache_dir``).

    Resolved via ``get_settings()`` (not a module-level snapshot) so it honors
    ``reload_settings()`` / ``MEDIA_PIPELINE_MODELS_CACHE_DIR`` (audit P1)."""
    root = get_settings().models_cache_dir
    return Path(root) if root is not None else Path("models")


def hf_cache_dir() -> Path:
    """The HuggingFace cache the snapshot models live in.

    Returns huggingface_hub's OWN default cache (honoring ``HF_HOME`` /
    ``HF_HUB_CACHE`` if the user set them), so a ``pull()`` and the runtime
    ``transformers.from_pretrained`` agree on one location without the app having
    to export anything (audit P0-3). The files-based ONNX taggers use
    ``models_root()`` instead — see the manifest ``dest`` dirs.
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE)
    except Exception:  # noqa: BLE001 — hub missing/old: fall back to the documented default
        return Path.home() / ".cache" / "huggingface" / "hub"


def _hf_repo_cache_name(repo_id: str) -> str:
    """HF cache folder name for a repo, e.g. ``models--google--siglip-...``."""
    return "models--" + repo_id.replace("/", "--")


def is_present(
    spec: ModelSpec, *, root: Path | None = None, hf_cache: Path | None = None
) -> bool | None:
    """Is this model already on disk?

    Returns True/False, or None for ``lib`` models (NudeNet) whose presence is
    managed by the third-party package and not reliably observable here.
    """
    root = root or models_root()
    hf_cache = hf_cache or hf_cache_dir()

    if spec.source == "lib":
        return None
    if spec.source == "url":
        assert spec.url and spec.dest
        fname = spec.url.rsplit("/", 1)[-1]
        return (root / spec.dest / fname).exists()
    # hf
    if spec.files is not None:
        assert spec.dest
        return all((root / spec.dest / f).exists() for f in spec.files)
    # snapshot into the HF cache: look for the repo folder with a snapshot inside.
    assert spec.repo_id
    repo_dir = hf_cache / _hf_repo_cache_name(spec.repo_id) / "snapshots"
    return repo_dir.is_dir() and any(repo_dir.iterdir())


def status(*, include_opt_in: bool = False) -> dict:
    """Present/absent for every model + an ``offline_ready`` flag.

    ``offline_ready`` is True when every REQUIRED model is on disk — i.e. the app
    can run without any further first-run download.
    """
    items = []
    required_missing = 0
    for spec in _manifest_for(include_opt_in):
        present = is_present(spec)
        items.append(
            {
                "key": spec.key,
                "title": spec.title,
                "required": spec.required,
                "present": present,
                "approx_size_mb": spec.approx_size_mb,
                "license": spec.license,
                "opt_in": spec.opt_in,
            }
        )
        if spec.required and present is False:
            required_missing += 1
    return {
        "models_root": str(models_root()),
        "offline_ready": required_missing == 0,
        "required_missing": required_missing,
        "models": items,
    }


def _manifest_for(include_opt_in: bool) -> list[ModelSpec]:
    """All models for display (optional always shown; opt-in only when asked)."""
    return selected(include_optional=True, include_opt_in=include_opt_in)


def plan(*, include_optional: bool = True, include_opt_in: bool = False) -> dict:
    """Dry-run: what a pull would fetch and roughly how big. No network."""
    specs = selected(include_optional=include_optional, include_opt_in=include_opt_in)
    missing = [s for s in specs if is_present(s) is not True]  # absent OR unknown(lib)
    return {
        "to_pull": [
            {
                "key": s.key,
                "title": s.title,
                "approx_size_mb": s.approx_size_mb,
                "source": s.source,
            }
            for s in missing
        ],
        "already_present": [s.key for s in specs if is_present(s) is True],
        "count": len(missing),
        "approx_total_mb": sum(s.approx_size_mb for s in missing),
        "approx_all_selected_mb": total_size_mb(specs),
    }


def _pull_one(spec: ModelSpec, *, root: Path, hf_cache: Path) -> dict:
    """Fetch a single model. Returns a result row; never raises on a fetch error."""
    if is_present(spec) is True:
        return {"key": spec.key, "status": "present", "message": "already on disk"}

    try:
        if spec.source == "url":
            assert spec.url and spec.dest
            _download_url(spec.url, root / spec.dest)
            return {"key": spec.key, "status": "pulled", "message": spec.url}

        if spec.source == "lib":
            # NudeNet: trigger the package's own first-use download. Only reached
            # when include_opt_in selected it (AGPL carve-out).
            from nudenet import NudeDetector  # noqa: F401  (lazy, optional dep)

            NudeDetector()  # side effect: fetches its ONNX
            return {
                "key": spec.key,
                "status": "pulled",
                "message": "via nudenet package",
            }

        # hf
        import huggingface_hub as hf

        assert spec.repo_id
        if spec.files is not None:
            assert spec.dest
            for fname in spec.files:
                hf.hf_hub_download(
                    repo_id=spec.repo_id,
                    filename=fname,
                    local_dir=str(root / spec.dest),
                    cache_dir=str(hf_cache),
                )
        else:
            hf.snapshot_download(repo_id=spec.repo_id, cache_dir=str(hf_cache))
        return {"key": spec.key, "status": "pulled", "message": spec.repo_id}

    except ImportError as exc:
        return {
            "key": spec.key,
            "status": "error",
            "message": f"missing dependency: {exc}",
        }
    except Exception as exc:  # noqa: BLE001 — classify, never crash the whole pull
        if _is_gated_or_auth_error(exc):
            return {
                "key": spec.key,
                "status": "error",
                "message": "gated/auth required — set an HF token (HF_TOKEN) and accept the model license",
            }
        return {
            "key": spec.key,
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
        }


def _is_gated_or_auth_error(exc: Exception) -> bool:
    """True for a HuggingFace gated-repo / 401 error. Prefers the typed
    huggingface_hub exceptions, falling back to a name/text sniff if the hub is
    absent or renames them (audit P2)."""
    try:
        from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

        if isinstance(exc, GatedRepoError):
            return True
        if isinstance(exc, HfHubHTTPError):
            resp = getattr(exc, "response", None)
            if getattr(resp, "status_code", None) in (401, 403):
                return True
    except Exception:  # noqa: BLE001 — hub missing/renamed: fall back to a sniff
        pass
    kind = type(exc).__name__
    return "Gated" in kind or "401" in str(exc) or "Unauthorized" in str(exc)


def pull(
    *,
    include_optional: bool = True,
    include_opt_in: bool = False,
    only: list[str] | None = None,
) -> dict:
    """Download missing weights. Resumable (HF native); errors are per-model.

    ``only`` restricts to specific manifest keys. ``include_opt_in`` is required
    to touch AGPL models (NudeNet).
    """
    root = models_root()
    hf_cache = hf_cache_dir()
    root.mkdir(parents=True, exist_ok=True)

    specs = selected(include_optional=include_optional, include_opt_in=include_opt_in)
    if only:
        wanted = set(only)
        specs = [s for s in specs if s.key in wanted]

    results = [_pull_one(s, root=root, hf_cache=hf_cache) for s in specs]
    return {
        "pulled": [r for r in results if r["status"] == "pulled"],
        "present": [r for r in results if r["status"] == "present"],
        "errors": [r for r in results if r["status"] == "error"],
        "results": results,
    }


def _download_url(url: str, dest_dir: Path) -> Path:
    """Stream a plain HTTP(S) file into ``dest_dir`` (atomic via .part)."""
    import urllib.request

    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = url.rsplit("/", 1)[-1]
    final = dest_dir / fname
    part = dest_dir / (fname + ".part")
    with urllib.request.urlopen(url) as resp, open(part, "wb") as fh:  # noqa: S310
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    part.replace(final)
    return final


def manifest_rows() -> list[dict]:
    """Manifest as plain dicts (for the wizard API / JSON)."""
    return [asdict(s) for s in selected(include_optional=True, include_opt_in=True)]
