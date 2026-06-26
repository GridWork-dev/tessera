"""Tests for first-run weight delivery (Spec E) — fully mocked, no network."""

from __future__ import annotations

import huggingface_hub as hf
import pytest

from pipeline.weights import delivery
from pipeline.weights.manifest import MANIFEST, by_key, selected, total_size_mb

# --- manifest integrity --------------------------------------------------------


def test_manifest_keys_unique_and_sane():
    keys = [s.key for s in MANIFEST]
    assert len(keys) == len(set(keys)), "duplicate manifest keys"
    assert all(s.approx_size_mb > 0 for s in MANIFEST)
    assert all(s.title and s.purpose and s.license for s in MANIFEST)


def test_required_models_present_in_manifest():
    required = {s.key for s in MANIFEST if s.required}
    assert {"siglip", "wd-eva02", "joytag"} <= required


def test_nudenet_is_opt_in_and_agpl():
    nn = by_key("nudenet")
    assert nn.opt_in is True
    assert nn.required is False
    assert "AGPL" in nn.license


# --- selection / size math -----------------------------------------------------


def test_selected_excludes_opt_in_by_default():
    keys = {s.key for s in selected()}
    assert "nudenet" not in keys
    assert "nudenet" in {s.key for s in selected(include_opt_in=True)}


def test_selected_required_only():
    keys = {s.key for s in selected(include_optional=False)}
    assert keys == {"siglip", "wd-eva02", "joytag"}


def test_total_size_grows_with_optional_and_opt_in():
    req = total_size_mb(include_optional=False)
    opt = total_size_mb(include_optional=True)
    both = total_size_mb(include_optional=True, include_opt_in=True)
    assert req < opt < both


# --- presence detection (filesystem) -------------------------------------------


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    root = tmp_path / "models"
    hfc = root / "hf"
    root.mkdir()
    monkeypatch.setattr(delivery, "models_root", lambda: root)
    monkeypatch.setattr(delivery, "hf_cache_dir", lambda: hfc)
    return root


def test_is_present_local_files(fake_root):
    jt = by_key("joytag")
    assert delivery.is_present(jt) is False
    dest = fake_root / jt.dest
    dest.mkdir(parents=True)
    for f in jt.files:
        (dest / f).write_text("x")
    assert delivery.is_present(jt) is True


def test_is_present_hf_snapshot(fake_root):
    sg = by_key("siglip")
    assert delivery.is_present(sg) is False
    snap = (
        fake_root
        / "hf"
        / delivery._hf_repo_cache_name(sg.repo_id)
        / "snapshots"
        / "abc"
    )
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_text("x")
    assert delivery.is_present(sg) is True


def test_is_present_lib_is_unknown(fake_root):
    assert delivery.is_present(by_key("nudenet")) is None


def test_status_offline_ready_when_required_present(fake_root):
    assert delivery.status()["offline_ready"] is False
    # place all three required models
    for key in ("joytag", "wd-eva02"):
        spec = by_key(key)
        d = fake_root / spec.dest
        d.mkdir(parents=True)
        for f in spec.files:
            (d / f).write_text("x")
    sg = by_key("siglip")
    snap = (
        fake_root
        / "hf"
        / delivery._hf_repo_cache_name(sg.repo_id)
        / "snapshots"
        / "abc"
    )
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_text("x")
    st = delivery.status()
    assert st["offline_ready"] is True
    assert st["required_missing"] == 0


# --- plan ----------------------------------------------------------------------


def test_plan_lists_missing_only(fake_root):
    p = delivery.plan(include_optional=False)
    assert p["count"] == 3  # all required missing
    assert p["approx_total_mb"] > 0
    # satisfy joytag -> drops out of the plan
    jt = by_key("joytag")
    d = fake_root / jt.dest
    d.mkdir(parents=True)
    for f in jt.files:
        (d / f).write_text("x")
    p2 = delivery.plan(include_optional=False)
    assert p2["count"] == 2
    assert "joytag" in p2["already_present"]


# --- pull (mocked hf_hub) ------------------------------------------------------


def test_pull_calls_hf_and_reports_pulled(fake_root, monkeypatch):
    calls = {"file": [], "snapshot": []}
    monkeypatch.setattr(
        hf,
        "hf_hub_download",
        lambda **kw: calls["file"].append((kw["repo_id"], kw["filename"])) or "ok",
    )
    monkeypatch.setattr(
        hf,
        "snapshot_download",
        lambda **kw: calls["snapshot"].append(kw["repo_id"]) or "ok",
    )
    out = delivery.pull(include_optional=False)  # siglip(snapshot) + joytag/wd(files)
    assert not out["errors"]
    assert len(out["pulled"]) == 3
    assert "google/siglip-so400m-patch14-384" in calls["snapshot"]
    assert ("fancyfeast/joytag", "model.onnx") in calls["file"]


def test_pull_only_restricts(fake_root, monkeypatch):
    monkeypatch.setattr(hf, "snapshot_download", lambda **kw: "ok")
    monkeypatch.setattr(hf, "hf_hub_download", lambda **kw: "ok")
    out = delivery.pull(only=["siglip"])
    assert [r["key"] for r in out["pulled"]] == ["siglip"]


def test_pull_gated_degrades_gracefully(fake_root, monkeypatch):
    class GatedRepoError(Exception):
        pass

    def boom(**kw):
        raise GatedRepoError("access to model is gated")

    monkeypatch.setattr(hf, "snapshot_download", boom)
    monkeypatch.setattr(hf, "hf_hub_download", lambda **kw: "ok")
    out = delivery.pull(only=["siglip"])
    assert len(out["errors"]) == 1
    assert "gated" in out["errors"][0]["message"].lower()


def test_pull_does_not_touch_nudenet_without_opt_in(fake_root, monkeypatch):
    monkeypatch.setattr(hf, "snapshot_download", lambda **kw: "ok")
    monkeypatch.setattr(hf, "hf_hub_download", lambda **kw: "ok")
    # url models would hit the network — stub the downloader
    monkeypatch.setattr(delivery, "_download_url", lambda url, dest: dest)
    out = delivery.pull(include_optional=True, include_opt_in=False)
    assert "nudenet" not in [r["key"] for r in out["results"]]
