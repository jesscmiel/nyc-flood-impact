"""Tests for P2.3 research corridor impassability graph."""

from __future__ import annotations

import json
from pathlib import Path

from flood_risk.risk.corridor_graph import default_ida_landmarks, dijkstra

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "figures" / "product_assets"


def test_corridor_json_has_three_landmark_pairs():
    path = ASSETS / "corridor_impassability.json"
    assert path.exists(), "run scripts/build_corridor_impassability.py"
    payload = json.loads(path.read_text())
    assert payload.get("official_closures") is False
    honesty = (payload.get("honesty") or "").lower()
    assert "not official" in honesty or "not an official" in honesty
    assert len(payload.get("landmarks") or []) == 3
    pairs = payload.get("pairs") or []
    assert len(pairs) == 3
    statuses = {p["status"] for p in pairs}
    assert "unsnapped" not in statuses
    assert any(
        s.startswith("cut_") or s in ("detour_around_deep", "open_research") for s in statuses
    )
    stats = payload.get("graph_stats") or {}
    assert stats.get("n_edges", 0) >= 100
    assert (ASSETS / "corridor_wet_edges.geojson").exists()
    assert (ASSETS / "corridor_research_paths.geojson").exists()


def test_dijkstra_blocks_impassable_edge():
    adj = {
        "a": [("b", 10.0, {"id": "ab", "impassable_deep": False})],
        "b": [
            ("a", 10.0, {"id": "ab", "impassable_deep": False}),
            ("c", 10.0, {"id": "bc", "impassable_deep": True}),
        ],
        "c": [("b", 10.0, {"id": "bc", "impassable_deep": True})],
    }
    open_p = dijkstra(adj, "a", "c")
    assert open_p["reachable"] is True
    adj2 = {
        "a": [("b", 10.0, {"id": "ab"})],
        "b": [("a", 10.0, {"id": "ab"})],
        "c": [],
    }
    blocked = dijkstra(adj2, "a", "c")
    assert blocked["reachable"] is False


def test_default_landmarks_match_shortlist_story():
    lms = default_ida_landmarks()
    ids = {lm.id for lm in lms}
    assert "stations:gtfs:F22" in ids
    assert "facilities:uid:a464e8e63eb8b2c92ab1995735cfd284" in ids
