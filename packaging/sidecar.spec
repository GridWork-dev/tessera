# PyInstaller spec for the FastAPI sidecar (Spec G, --onedir).
# Run from the repo root:
#   ./venv/bin/python -m PyInstaller packaging/sidecar.spec --noconfirm
#
# First-pass goal: freeze the SERVER path (browse/search/serve-SPA against the
# existing catalog). The heavy ML tiers (torch/onnxruntime/mlx) are lazy and are
# NOT force-collected here — they're a follow-on once the server sidecar boots.
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = Path(SPECPATH).parent  # spec lives in packaging/ → repo root

# uvicorn + webui have dynamic imports (protocol/loop plugins, split routers).
hidden = collect_submodules("uvicorn") + collect_submodules("webui")

datas = []
mig = ROOT / "pipeline" / "migrations"
if mig.exists():
    datas.append((str(mig), "pipeline/migrations"))
dist = ROOT / "frontend" / "dist"
if dist.exists():
    datas.append((str(dist), "frontend/dist"))
for cfg in ("defaults.yaml",):
    p = ROOT / cfg
    if p.exists():
        datas.append((str(p), "."))

# Native extensions ship as binaries (sqlite-vec loadable ext, turbovec).
binaries = []
for pkg in ("sqlite_vec", "turbovec"):
    try:
        binaries += collect_dynamic_libs(pkg)
        datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "sidecar.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mp-sidecar",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="mp-sidecar")
