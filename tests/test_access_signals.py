"""Unit tests for demo geography demotion + access-signal joins."""

from __future__ import annotations

from flood_risk.risk.access_signals import (
    apply_access_and_demotion,
    apply_demo_geography_ranks,
    is_nj_turnpike_noise,
    is_nyc_demo_geography,
)


def test_turnpike_demoted_below_nyc():
    assets = [
        {
            "id": "road:tp",
            "name": "New Jersey Turnpike",
            "max_depth_m": 0.14,
            "max_depth_cm": 14.0,
            "lon": -74.12,
            "lat": 40.72,
            "band": "deep_ponding",
            "asset_type": "road",
        },
        {
            "id": "road:vw",
            "name": "Van Wyck Expressway",
            "max_depth_m": 0.094,
            "max_depth_cm": 9.4,
            "lon": -73.837,
            "lat": 40.740,
            "band": "deep_ponding",
            "asset_type": "road",
        },
    ]
    ranked = apply_demo_geography_ranks(assets)
    assert ranked[0]["id"] == "road:vw"
    assert ranked[1]["id"] == "road:tp"
    assert ranked[1]["demo_demoted"] is True
    assert is_nj_turnpike_noise(assets[0])
    assert is_nyc_demo_geography(assets[1])


def test_explicit_join_sets_limited_access():
    payload = {
        "assets": [
            {
                "id": "stations:194:Smith–9th Streets",
                "name": "Smith–9th Streets",
                "max_depth_m": 0.111,
                "max_depth_cm": 11.1,
                "lon": -73.996,
                "lat": 40.674,
                "band": "deep_ponding",
                "asset_type": "station",
                "layer": "stations",
            }
        ]
    }
    fixture = {
        "id": "t",
        "honesty": "research",
        "sources": ["mta_alerts"],
        "joins": [
            {
                "asset_id": "stations:194:Smith–9th Streets",
                "access": "limited",
                "signals": [{"source": "mta_alerts", "label": "alert", "access": "limited"}],
            }
        ],
    }
    apply_access_and_demotion(payload, fixture)
    a = payload["assets"][0]
    assert a["access_status"] == "limited"
    assert a["limited_access_flag"] is True
    assert a["access_signals"]
