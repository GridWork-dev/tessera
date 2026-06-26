"""
Smoke tests for FastAPI webui endpoints.
"""

# Add project root to path
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))
from webui import routes_dashboard
from webui.main import app

client = TestClient(app)


class TestStatsEndpoint:
    """GET /api/stats."""

    def test_stats_returns_200(self):
        """Stats endpoint returns 200 with expected keys."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_images" in data
        assert "processed_images" in data
        assert "people_count" in data
        assert isinstance(data["total_images"], int)

    def test_tag_categories_matches_facets(self):
        """tag_categories == distinct categories the facets endpoint reports.

        Both must derive from COUNT(DISTINCT tags.category); the old set-based
        stats query and the facets group-by must agree on the same number.
        """
        stats = client.get("/api/stats").json()
        facets = client.get("/api/facets").json()
        # /api/facets `categories` is keyed by distinct category; its length is
        # the same distinct-category count /api/stats reports.
        assert stats["tag_categories"] == len(facets["categories"])
        assert isinstance(stats["tag_categories"], int)


class TestPipelineEndpoint:
    """GET /api/pipeline."""

    def test_pipeline_shape(self):
        """Per-tier progress with consistent count/total/pct shape."""
        response = client.get("/api/pipeline")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        total = data["total"]

        # tier0_3 uses processed/total; tier1/2/3 use count/total.
        t0 = data["tier0_3"]
        assert set(t0) >= {"processed", "total", "pct", "running"}
        assert t0["total"] == total
        assert 0 <= t0["pct"] <= 100
        assert isinstance(t0["running"], bool)

        for key in ("tier1", "tier2", "tier3"):
            tier = data[key]
            assert "count" in tier
            assert tier["total"] == total
            assert 0 <= tier["pct"] <= 100
            assert tier["count"] <= total

    def test_pipeline_pct_consistent_with_count(self):
        """pct is count/total*100 (within rounding) for each count-based tier."""
        data = client.get("/api/pipeline").json()
        total = data["total"]
        if total == 0:
            return
        for key in ("tier1", "tier2", "tier3"):
            tier = data[key]
            expected = round(tier["count"] / total * 100, 1)
            assert tier["pct"] == expected


class TestSystemEndpoint:
    """GET /api/system."""

    def test_system_returns_200(self):
        """System telemetry returns 200 with the always-present keys."""
        response = client.get("/api/system")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "tagger_running" in data
        assert isinstance(data["tagger_running"], bool)

    def test_system_with_psutil(self, monkeypatch):
        """With psutil mocked, telemetry fields are populated and well-shaped."""
        import types

        fake = types.SimpleNamespace(
            cpu_percent=lambda interval=None, percpu=False: (
                [10.0, 20.0] if percpu else 15.0
            ),
            cpu_count=lambda logical=True: 8,
            virtual_memory=lambda: types.SimpleNamespace(
                used=4_000_000_000, total=16_000_000_000, percent=25.0
            ),
            disk_usage=lambda path: types.SimpleNamespace(
                free=500_000_000_000, total=1_000_000_000_000, percent=50.0
            ),
            process_iter=lambda attrs=None: iter([]),
        )
        monkeypatch.setitem(sys.modules, "psutil", fake)

        data = client.get("/api/system").json()
        assert data["available"] is True
        assert data["cpu_percent"] == 15.0
        assert data["cpu_count"] == 8
        assert data["per_cpu_percent"] == [10.0, 20.0]
        assert data["virtual_memory"] == {
            "used": 4_000_000_000,
            "total": 16_000_000_000,
            "pct": 25.0,
        }
        assert data["disk_usage"]["pct"] == 50.0

    def test_system_without_psutil(self, monkeypatch):
        """Missing psutil degrades gracefully — never 500s."""
        # Force the import inside the route to fail.
        real_import = (
            __builtins__["__import__"]
            if isinstance(__builtins__, dict)
            else __builtins__.__import__
        )

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not installed (simulated)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setitem(sys.modules, "psutil", None)
        monkeypatch.setattr("builtins.__import__", fake_import)

        response = client.get("/api/system")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "tagger_running" in data

    def test_tagger_running_uses_pgrep_fallback(self, monkeypatch):
        """_tagger_running falls back to pgrep when psutil is absent."""
        import subprocess

        monkeypatch.setitem(sys.modules, "psutil", None)
        real_import = (
            __builtins__["__import__"]
            if isinstance(__builtins__, dict)
            else __builtins__.__import__
        )

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)

        # pgrep returns 0 -> running True; 1 -> running False.
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: types_run(returncode=0),
        )
        assert routes_dashboard._tagger_running() is True

        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: types_run(returncode=1),
        )
        assert routes_dashboard._tagger_running() is False


def types_run(returncode: int):
    """Tiny stand-in for subprocess.CompletedProcess (only returncode used)."""
    import types

    return types.SimpleNamespace(returncode=returncode)


class TestFacetsEndpoint:
    """GET /api/facets."""

    def test_facets_returns_200(self):
        """Facets endpoint returns 200 with dict structure."""
        response = client.get("/api/facets")
        assert response.status_code == 200
        data = response.json()
        assert "people" in data
        assert isinstance(data["people"], dict)


class TestImagesEndpoint:
    """GET /api/images."""

    def test_images_default_returns_list(self):
        """GET /api/images returns paginated results."""
        response = client.get("/api/images")
        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        assert "total" in data
        assert isinstance(data["images"], list)

    def test_images_with_limit(self):
        """GET /api/images?limit=5 returns at most 5 images."""
        response = client.get("/api/images?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["images"]) <= 5


class TestImageNotFound:
    """404 handling."""

    def test_image_content_nonexistent(self):
        """GET /api/images/999999/content → 404."""
        response = client.get("/api/images/999999/content")
        assert response.status_code == 404

    def test_unmatched_api_route_404s_not_spa(self):
        """Unmatched /api/* must 404 — never fall through to the SPA shell.

        Regression: once frontend/dist exists the catch-all SPA route is
        registered; without a reserved-prefix guard it returned index.html
        (HTTP 200) for any unmatched /api path, masking real 404s as HTML.
        """
        response = client.get("/api/totally-bogus-endpoint")
        assert response.status_code == 404


class TestGridEndpoints:
    """GET /api/grids and POST /api/grids."""

    def test_get_grids_returns_200(self):
        """GET /api/grids returns list."""
        response = client.get("/api/grids")
        assert response.status_code == 200
        data = response.json()
        assert "grids" in data

    def test_create_grid_bad_layout(self):
        """POST /api/grids with invalid layout → 422 or 400."""
        response = client.post(
            "/api/grids",
            data={"image_ids": "1,2,3,4", "layout": "invalid_layout"},
        )
        assert response.status_code >= 400
