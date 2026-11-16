"""Golden checks for Henri Event parity (radar + inventory + shortlist + compare)."""

from __future__ import annotations

import json
from pathlib import Path

from flood_risk.risk.demo_shortlist import demo_shortlist_ids

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "figures" / "product_assets"


def test_henri_desk_uses_official_shortlist_ids():
    path = ASSETS / "decision_desk_assets_henri.json"
    assert path.exists(), "run scripts/build_henri_parity.py first"
    desk = json.loads(path.read_text())
    by_id = {a["id"]: a for a in desk.get("assets") or []}
    assert "stations:gtfs:F22" in by_id
    wet_hits = 0
    for aid in demo_shortlist_ids():
        assert aid in by_id, f"shortlist id missing from Henri desk: {aid}"
        a = by_id[aid]
        if a.get("henri_dry_stub") or a.get("band") == "below_band":
            assert float(a.get("max_depth_cm") or 0) < 3.0
        else:
            assert float(a.get("max_depth_cm") or 0) > 0
            wet_hits += 1
    assert wet_hits >= 3


def test_henri_shortlist_bundle_maps_ida_ids():
    path = ASSETS / "decision_desk_shortlist_henri.json"
    assert path.exists()
    bundle = json.loads(path.read_text())
    assert bundle.get("event_id") == "henri-2021"
    ids = demo_shortlist_ids()
    assert bundle.get("shortlist_ids") == ids
    covered = set(bundle.get("shortlist_ids_present") or []) | set(
        bundle.get("shortlist_ids_below_band") or []
    )
    assert set(ids).issubset(covered)
    assert not (bundle.get("shortlist_ids_missing") or [])
    by_id = {a["id"]: a for a in bundle.get("assets") or []}
    for aid in ids:
        assert aid in by_id


def test_henri_radar_loop_frames_exist():
    meta = json.loads((ASSETS / "henri_radar_meta.json").read_text())
    assert meta.get("n_frames", 0) >= 12
    manifest = json.loads((ASSETS / "product_manifest.json").read_text())
    henri_path = next(p for p in manifest["storm_paths"] if p["id"] == "mrms_qpe_henri")
    frames = henri_path["precip"]["frames"]
    assert len(frames) >= 12
    for fr in frames[::6]:
        assert (ASSETS / fr["png"]).exists(), fr["png"]
    assert (ASSETS / henri_path["precip"]["storm_total_png"]).exists()


def test_henri_parity_unhides_event_in_manifest_and_html():
    manifest = json.loads((ASSETS / "product_manifest.json").read_text())
    ss = manifest.get("second_storm") or {}
    assert ss.get("available") is True
    assert ss.get("parity") is True
    desk = manifest.get("asset_decision_desk") or {}
    assert desk.get("henri_parity") is True
    henri_ev = (desk.get("events") or {}).get("henri-2021") or {}
    assert henri_ev.get("storm_path_id") == "mrms_qpe_henri"
    assert henri_ev.get("shortlist_json") == "decision_desk_shortlist_henri.json"
    html = (ROOT / "figures" / "product_map.html").read_text()
    assert "Henri (hidden until parity)" not in html or "henriParity" in html
    assert "applyStormPathForEvent" in html
    assert "ida_henri_compare_strip" in html or "selCompareStrip" in html
    assert 'eventSel.disabled = !(henriParity && secondStorm.available)' in html


def test_ida_henri_compare_strip_shortlist():
    path = ASSETS / "ida_henri_compare_strip.json"
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload.get("n_shortlist_both", 0) >= 4
    rows = {r["id"]: r for r in payload.get("shortlist") or []}
    for aid in demo_shortlist_ids():
        assert aid in rows
        assert rows[aid]["present_in"] == "both"
        assert rows[aid]["ida_cm"] is not None
        assert rows[aid]["henri_cm"] is not None
