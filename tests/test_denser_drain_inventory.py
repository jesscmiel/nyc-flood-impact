"""P2.5 denser open drain inventory checks (not SWMM)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "figures" / "product_assets"
INFRA = ROOT / "data" / "raw" / "infrastructure"


def test_open_drain_inventory_is_dense():
    geo = json.loads((INFRA / "osm_drains_metro.geojson").read_text())
    n = len(geo.get("features") or [])
    assert n >= 100_000, f"expected dense open catch-basin inventory, got {n}"
    sources = {(f.get("properties") or {}).get("source") for f in geo["features"][:2000]}
    assert any("catch_basin" in str(s) or "nyc_open" in str(s) for s in sources)


def test_dense_product_sample_and_meta():
    sample = ASSETS / "dep_catch_basins_dense_sample.geojson"
    assert sample.exists(), "run scripts/build_denser_drain_inventory.py"
    geo = json.loads(sample.read_text())
    assert len(geo.get("features") or []) >= 2000
    meta = json.loads((ASSETS / "denser_drain_inventory_meta.json").read_text())
    assert meta.get("not_swmm") is True
    assert meta.get("not_dep_sewer") is True
    cov = (meta.get("drain_points") or {}).get("coverage") or {}
    legacy = (meta.get("drain_points") or {}).get("coverage_legacy_buffer") or {}
    assert cov.get("fraction_with_drain_credit", 0) >= legacy.get("fraction_with_drain_credit", 0)
    assert meta.get("drain_points", {}).get("n", 0) >= 100_000


def test_manifest_points_at_dense_sample():
    m = json.loads((ASSETS / "product_manifest.json").read_text())
    d = m.get("drainage_capacity_proxy") or {}
    assert d.get("not_swmm") is True
    assert "dense" in str(d.get("dense_sample_geojson") or "")
