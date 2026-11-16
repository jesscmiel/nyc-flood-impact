"""P2.6 nested SFINCS feathered exchange + non-peer HAND calib."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flood_risk.inundation.sfincs_nested import feathered_nest_exchange

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "figures" / "product_assets"


def test_feathered_exchange_prefers_nest_interior():
    coarse = np.full((20, 20), 1.0, dtype=np.float32)
    nest = np.full((20, 20), np.nan, dtype=np.float32)
    nest[6:14, 6:14] = 3.0
    out, stats = feathered_nest_exchange(coarse, nest, feather_px=3)
    assert stats["mode"] == "feathered_boundary_exchange"
    assert abs(float(out[10, 10]) - 3.0) < 1e-5
    assert abs(float(out[0, 0]) - 1.0) < 1e-5


def test_exchange_artifacts_shipped():
    path = ASSETS / "sfincs_nest_exchange.json"
    assert path.exists(), "run scripts/build_sfincs_nest_exchange.py"
    payload = json.loads(path.read_text())
    assert payload.get("not_swmm") is True
    assert payload.get("primary_remains") == "pysheds_hand_bathtub_v2"
    assert (payload.get("exchange") or {}).get("mode") == "feathered_boundary_exchange"
    calib = payload.get("hand_overlap_calib_non_peer") or {}
    assert calib.get("non_peer") is True
    meta = json.loads((ASSETS / "depth_sfincs_metro_nested_ida_meta.json").read_text())
    assert meta.get("never_blend_into_hand") is True
    assert "exchange" in meta
