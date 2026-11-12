"""Tests for live access feed normalization + fixture fallback."""

from __future__ import annotations

from flood_risk.risk.live_access_feeds import (
    _alert_access,
    _free_flow_prior,
    _parse_link_point,
    build_live_access_fixture,
    merge_live_over_fixture,
)


def test_parse_link_point_metro():
    pts = _parse_link_point("40.7401,-73.8371 40.741,-73.836")
    assert pts is not None
    lon, lat = pts
    assert abs(lon + 73.8371) < 1e-6
    assert abs(lat - 40.7401) < 1e-6


def test_parse_link_point_rejects_far():
    assert _parse_link_point("41.9,-87.6") is None


def test_free_flow_prior_highway():
    assert _free_flow_prior("Van Wyck Expressway") >= 40
    assert _free_flow_prior("Myrtle Avenue") <= 30


def test_alert_access_limited_language():
    assert _alert_access("Delays", "Coney Island-bound F skips Smith-9 Sts") == "limited"
    assert _alert_access("Delays", "trains are running with delays") == "watch"


def test_build_live_falls_back_to_fixture(monkeypatch):
    fixture = {
        "id": "ida_access_signals_v1",
        "honesty": "fixture",
        "dot_speeds": [{"id": "dot:x"}],
        "events_511": [],
        "mta_alerts": [],
        "joins": [],
    }

    def boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "flood_risk.risk.live_access_feeds.fetch_dot_speeds", boom
    )
    monkeypatch.setattr(
        "flood_risk.risk.live_access_feeds.fetch_nysdot_511_events",
        lambda **_k: ([], {"ok": False}),
    )
    monkeypatch.setattr(
        "flood_risk.risk.live_access_feeds.fetch_street_closures_as_511_style", boom
    )
    monkeypatch.setattr(
        "flood_risk.risk.live_access_feeds.fetch_mta_alerts", boom
    )
    out = build_live_access_fixture(fixture_fallback=fixture)
    assert out["id"] == "ida_access_signals_v1"
    assert out["live_status"]["mode"] == "fixture_fallback"
    assert out["dot_speeds"][0]["id"] == "dot:x"


def test_merge_keeps_fixture_joins():
    live = {
        "id": "access_signals_live_v1",
        "mode": "live",
        "dot_speeds": [],
        "events_511": [],
        "mta_alerts": [],
        "joins": [],
    }
    fixture = {
        "id": "ida_access_signals_v1",
        "joins": [{"asset_id": "road:1", "access": "limited"}],
    }
    merged = merge_live_over_fixture(live, fixture)
    assert merged["joins"][0]["asset_id"] == "road:1"
