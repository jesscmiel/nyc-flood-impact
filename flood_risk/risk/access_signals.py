"""Research limited-access signals for Asset Decision Desk (Ida replay).

Joins open-data-style fixtures (NYC DOT speeds, 511-style closures, MTA alerts)
onto ranked wet assets. NOT official DOT / NYSDOT / MTA closures.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# Rough NYC borough preference (includes Staten Island; excludes NJ Turnpike corridor).
NYC_BBOX = (-74.28, 40.48, -73.68, 40.93)
# West-of-Hudson NJ mainland (exclude except SI south of ~40.65).
NJ_MAINLAND_WEST = -74.05


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def is_nj_turnpike_noise(asset: dict[str, Any]) -> bool:
    name = str(asset.get("name") or "").lower()
    return "turnpike" in name or "new jersey turnpike" in name


def is_nyc_demo_geography(asset: dict[str, Any]) -> bool:
    """Prefer NYC boroughs / SI for demo ranking; demote NJ mainland noise."""
    if is_nj_turnpike_noise(asset):
        return False
    lon = asset.get("lon")
    lat = asset.get("lat")
    if lon is None or lat is None:
        return True
    lon_f, lat_f = float(lon), float(lat)
    west, south, east, north = NYC_BBOX
    if not (west <= lon_f <= east and south <= lat_f <= north):
        return False
    # Keep Staten Island; drop NJ mainland west of Hudson.
    if lon_f < NJ_MAINLAND_WEST and lat_f >= 40.65:
        return False
    return True


def demo_sort_key(asset: dict[str, Any]) -> tuple:
    """Sort: NYC-preferred first, then deeper, then name."""
    demoted = 0 if is_nyc_demo_geography(asset) else 1
    depth = -float(asset.get("max_depth_m") or 0.0)
    name = str(asset.get("name") or "")
    return (demoted, depth, name)


def apply_demo_geography_ranks(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(assets, key=demo_sort_key)
    for i, a in enumerate(ranked, start=1):
        a["rank"] = i
        a["demo_demoted"] = not is_nyc_demo_geography(a)
        a["nyc_demo_geography"] = not a["demo_demoted"]
    return ranked


def _access_rank(status: str) -> int:
    order = {"limited": 3, "watch": 2, "open": 1}
    return order.get(status, 0)


def join_access_signals(
    assets: list[dict[str, Any]],
    fixture: dict[str, Any],
    *,
    buffer_m: float = 100.0,
) -> dict[str, Any]:
    """Attach access_status / access_signals onto assets from fixture joins + geometry.

    Explicit fixture ``joins`` win; otherwise buffer-match speeds/events/alerts.
    """
    joins_by_id = {
        str(j["asset_id"]): j
        for j in (fixture.get("joins") or [])
        if j.get("asset_id")
    }
    speeds = list(fixture.get("dot_speeds") or [])
    events = list(fixture.get("events_511") or [])
    alerts = list(fixture.get("mta_alerts") or [])
    deep_bands = {"deep_ponding", "hazard"}

    joined_n = 0
    for a in assets:
        aid = str(a.get("id") or "")
        signals: list[dict[str, Any]] = []
        status = "open"

        explicit = joins_by_id.get(aid)
        if explicit:
            status = str(explicit.get("access") or "watch")
            for s in explicit.get("signals") or []:
                signals.append(dict(s))
        else:
            lon, lat = a.get("lon"), a.get("lat")
            if lon is not None and lat is not None:
                for sp in speeds:
                    slon, slat = sp.get("lon"), sp.get("lat")
                    if slon is None or slat is None:
                        continue
                    if haversine_m(float(lon), float(lat), float(slon), float(slat)) <= buffer_m:
                        ratio = sp.get("speed_ratio")
                        st = "limited" if ratio is not None and float(ratio) < 0.35 else "watch"
                        signals.append(
                            {
                                "source": "nyc_dot_speeds",
                                "id": sp.get("id"),
                                "label": sp.get("label") or "DOT speed slowdown",
                                "speed_ratio": ratio,
                                "access": st,
                            }
                        )
                        if _access_rank(st) > _access_rank(status):
                            status = st
                for ev in events:
                    elon, elat = ev.get("lon"), ev.get("lat")
                    if elon is None or elat is None:
                        continue
                    if haversine_m(float(lon), float(lat), float(elon), float(elat)) <= buffer_m:
                        st = "limited" if ev.get("closure") else "watch"
                        signals.append(
                            {
                                "source": "nysdot_511_events",
                                "id": ev.get("id"),
                                "label": ev.get("label") or "511-style event",
                                "access": st,
                            }
                        )
                        if _access_rank(st) > _access_rank(status):
                            status = st
                if a.get("asset_type") == "station":
                    for al in alerts:
                        match_ids = set(al.get("asset_ids") or [])
                        match_names = {str(n).lower() for n in (al.get("station_names") or [])}
                        name_l = str(a.get("name") or "").lower()
                        if aid in match_ids or name_l in match_names:
                            st = str(al.get("access") or "watch")
                            signals.append(
                                {
                                    "source": "mta_alerts",
                                    "id": al.get("id"),
                                    "label": al.get("label") or "MTA service alert",
                                    "access": st,
                                }
                            )
                            if _access_rank(st) > _access_rank(status):
                                status = st

        # Research rule: escalate limited only when deep band + ops signal agree.
        band = a.get("band")
        if status == "limited" and band not in deep_bands and not explicit:
            status = "watch"

        a["access_status"] = status if signals or explicit else "open"
        a["access_signals"] = signals
        a["limited_access_flag"] = a["access_status"] == "limited"
        if signals or explicit:
            joined_n += 1

    return {
        "joined_assets": joined_n,
        "buffer_m": buffer_m,
        "fixture_id": fixture.get("id"),
        "honesty": fixture.get("honesty"),
    }


def load_access_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def apply_access_and_demotion(
    payload: dict[str, Any],
    fixture: dict[str, Any] | None,
    *,
    buffer_m: float = 100.0,
) -> dict[str, Any]:
    """Mutate desk payload: demote NJ Turnpike-class tops, join access chips."""
    assets = list(payload.get("assets") or [])
    assets = apply_demo_geography_ranks(assets)
    access_meta: dict[str, Any] = {
        "enabled": False,
        "note": "No access fixture applied",
    }
    if fixture:
        access_meta = join_access_signals(assets, fixture, buffer_m=buffer_m)
        access_meta["enabled"] = True
        access_meta["honesty"] = fixture.get("honesty")
        access_meta["sources"] = fixture.get("sources")
        access_meta["replay"] = fixture.get("replay")
    payload["assets"] = assets
    payload["access_signals"] = access_meta
    payload["demo_geography"] = {
        "prefer_nyc": True,
        "demote_nj_turnpike": True,
        "bbox": list(NYC_BBOX),
        "note": (
            "Demo ranking demotes New Jersey Turnpike / non-NYC mainland noise "
            "so All-mode tops stay NYC-memorable. Depths unchanged."
        ),
    }
    if assets:
        payload["all_wet_summary"] = {
            "n": len(assets),
            "max_depth_m": assets[0]["max_depth_m"],
            "deepest_name": assets[0]["name"],
        }
    return payload
