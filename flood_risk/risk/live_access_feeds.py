"""Live / fresher access feeds for Asset Decision Desk (ops path).

Fetches NYC DOT Traffic Speeds, NYSDOT 511 events (when keyed), NYC street
closures as 511-style fallback, and MTA GTFS-RT service alerts. Normalizes to
the same shape as ``access_signals_ida_fixture.json`` so join logic is shared.

Ida fixtures remain the demo default; live feeds are opt-in / Advanced.
Research only — NOT official closures / NOT decision-grade.

Bus Time (skipped): MTA Bus Time ``vehiclePositions`` needs
``MTA_BUS_TIME_API_KEY``. This environment has no key, so live bus vehicles
are intentionally not fetched. Subway GTFS-RT VehiclePositions are keyless but
also deferred — alerts + DOT speeds already carry the access story.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from flood_risk.risk.access_signals import NYC_BBOX, haversine_m

# Documented skip — do not call Bus Time without an explicit key.
BUS_TIME_SKIPPED = {
    "status": "skipped",
    "source": "mta_bus_time_vehicle_positions",
    "env_var": "MTA_BUS_TIME_API_KEY",
    "reason": "API key not configured; Bus Time vehicle map deferred",
    "docs": (
        "https://bustime.mta.info/wiki/Developers/Index — requires developer key. "
        "Product uses DOT speeds + 511-style closures + MTA service alerts instead."
    ),
}

DOT_SPEEDS_URL = "https://data.cityofnewyork.us/resource/i4gi-tjb9.json"
STREET_CLOSURES_URL = "https://data.cityofnewyork.us/resource/i6b5-j7bu.json"
MTA_ALERTS_JSON_URL = (
    "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fall-alerts.json"
)
NYSDOT_511_EVENTS_URL = "https://511ny.org/api/getevents"

# Free-flow priors when DOT feed has no free-flow field (research heuristic).
_FREE_FLOW_HWY = 45.0
_FREE_FLOW_ARTERIAL = 25.0
_SLOW_RATIO = 0.55
_LIMITED_RATIO = 0.35

_HWY_RE = re.compile(
    r"expressway|parkway|highway|turnpike|thruway|bridge|tunnel|fdr|bqe|belt",
    re.I,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _in_metro(lon: float, lat: float) -> bool:
    west, south, east, north = NYC_BBOX
    # Slightly wider for SI / outer Queens arterials in the DOT feed.
    return (west - 0.05) <= lon <= (east + 0.08) and (south - 0.02) <= lat <= (north + 0.05)


def _parse_link_point(link_points: str | None) -> tuple[float, float] | None:
    if not link_points:
        return None
    # DOT link_points are "lat,lon lat,lon …"
    first = link_points.strip().split()[0]
    parts = first.split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not _in_metro(lon, lat):
        return None
    return lon, lat


def _free_flow_prior(link_name: str | None) -> float:
    name = link_name or ""
    return _FREE_FLOW_HWY if _HWY_RE.search(name) else _FREE_FLOW_ARTERIAL


def fetch_dot_speeds(
    *,
    limit: int = 2000,
    timeout_s: float = 45.0,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    resp = sess.get(DOT_SPEEDS_URL, params={"$limit": limit}, timeout=timeout_s)
    resp.raise_for_status()
    rows = resp.json()
    out: list[dict[str, Any]] = []
    for row in rows:
        pts = _parse_link_point(row.get("link_points"))
        if pts is None:
            continue
        lon, lat = pts
        try:
            speed = float(row.get("speed") or 0.0)
        except (TypeError, ValueError):
            continue
        if speed <= 0:
            continue
        link_name = str(row.get("link_name") or "")
        free = _free_flow_prior(link_name)
        ratio = speed / free if free > 0 else 1.0
        if ratio >= _SLOW_RATIO:
            continue  # keep payload focused on access stress
        out.append(
            {
                "id": f"dot:live:{row.get('link_id') or row.get('id')}",
                "label": f"{link_name or 'DOT link'} · {speed:.0f}/{free:.0f} mph (live)",
                "lon": round(lon, 5),
                "lat": round(lat, 5),
                "speed_mph": round(speed, 2),
                "free_flow_mph": free,
                "speed_ratio": round(ratio, 3),
                "link_name": link_name,
                "data_as_of": row.get("data_as_of"),
                "borough": row.get("borough"),
                "access": "limited" if ratio < _LIMITED_RATIO else "watch",
            }
        )
    out.sort(key=lambda r: float(r["speed_ratio"]))
    return out[:400]


def fetch_nysdot_511_events(
    *,
    api_key: str | None = None,
    timeout_s: float = 45.0,
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (events, meta). Empty events when key missing / request fails."""
    key = api_key if api_key is not None else os.environ.get("NYSDOT_511_API_KEY", "").strip()
    meta: dict[str, Any] = {"source": "nysdot_511_events", "ok": False}
    if not key:
        meta["note"] = "NYSDOT_511_API_KEY unset — use street-closures fallback"
        return [], meta
    sess = session or requests.Session()
    try:
        resp = sess.get(
            NYSDOT_511_EVENTS_URL,
            params={"key": key, "format": "json"},
            timeout=timeout_s,
        )
        if resp.status_code >= 400:
            meta["http_status"] = resp.status_code
            meta["note"] = "511 GetEvents rejected key or endpoint"
            return [], meta
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        meta["note"] = f"511 fetch error: {exc}"
        return [], meta

    rows = payload if isinstance(payload, list) else payload.get("events") or payload.get("getevents") or []
    out: list[dict[str, Any]] = []
    for ev in rows:
        lat = ev.get("Latitude") or ev.get("latitude") or (ev.get("Geography") or {}).get("Latitude")
        lon = ev.get("Longitude") or ev.get("longitude") or (ev.get("Geography") or {}).get("Longitude")
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not _in_metro(lon_f, lat_f):
            continue
        etype = str(ev.get("EventType") or ev.get("event_type") or ev.get("Type") or "incident")
        desc = str(ev.get("Description") or ev.get("description") or ev.get("Headline") or etype)
        lanes = str(ev.get("LanesAffected") or ev.get("lanes_affected") or "")
        closure = bool(
            ev.get("IsFullClosure")
            or "clos" in etype.lower()
            or "clos" in desc.lower()
            or "closed" in lanes.lower()
        )
        road = str(ev.get("RoadwayName") or ev.get("road") or "")
        eid = ev.get("ID") or ev.get("id") or f"{lon_f:.3f},{lat_f:.3f}"
        out.append(
            {
                "id": f"511:live:{eid}",
                "label": f"511 · {desc[:120]}",
                "lon": round(lon_f, 5),
                "lat": round(lat_f, 5),
                "closure": closure,
                "event_type": etype,
                "road": road,
                "access": "limited" if closure else "watch",
            }
        )
    meta["ok"] = True
    meta["n"] = len(out)
    return out, meta


def fetch_street_closures_as_511_style(
    *,
    limit: int = 500,
    timeout_s: float = 45.0,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """NYC Open Data street closures — construction context, not emergency flood closures."""
    sess = session or requests.Session()
    resp = sess.get(STREET_CLOSURES_URL, params={"$limit": limit}, timeout=timeout_s)
    resp.raise_for_status()
    rows = resp.json()
    out: list[dict[str, Any]] = []
    for row in rows:
        geom = row.get("the_geom") or {}
        coords = None
        if geom.get("type") == "MultiLineString":
            try:
                coords = geom["coordinates"][0][0]
            except (IndexError, KeyError, TypeError):
                coords = None
        elif geom.get("type") == "Point":
            coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not _in_metro(lon, lat):
            continue
        street = str(row.get("onstreetname") or "street")
        purpose = str(row.get("purpose") or "construction")
        out.append(
            {
                "id": f"511:closure:{row.get('uniqueid') or row.get('segmentid')}",
                "label": f"Street closure · {street.title()} ({purpose[:60]}) — construction context",
                "lon": round(lon, 5),
                "lat": round(lat, 5),
                "closure": True,
                "event_type": "construction_closure",
                "road": street,
                "access": "limited",
                "work_start_date": row.get("work_start_date"),
                "work_end_date": row.get("work_end_date"),
            }
        )
    return out[:250]


def _alert_text(alert: dict[str, Any]) -> str:
    hdr = alert.get("header_text") or {}
    parts = []
    for tr in hdr.get("translation") or []:
        if (tr.get("language") or "").startswith("en") and "html" not in (tr.get("language") or ""):
            parts.append(tr.get("text") or "")
    if not parts:
        for tr in hdr.get("translation") or []:
            parts.append(re.sub(r"<[^>]+>", "", tr.get("text") or ""))
    return " ".join(parts).strip()


def _alert_access(alert_type: str, text: str) -> str:
    blob = f"{alert_type} {text}".lower()
    if any(
        k in blob
        for k in (
            "suspend",
            "no trains",
            "closed",
            "skips",
            "skip ",
            "station closed",
            "entrance is closed",
            "service is suspended",
        )
    ):
        return "limited"
    return "watch"


# Common desk station names → loose match tokens for live alert text.
_STATION_MATCHERS: list[tuple[str, list[str]]] = [
    ("Smith–9th Streets", ["smith-9", "smith–9", "smith 9", "smith-9th", "smith–9th"]),
    ("Myrtle Avenue", ["myrtle"]),
    ("36th Street", ["36th street", "36 st"]),
]


def fetch_mta_alerts(
    *,
    timeout_s: float = 45.0,
    session: requests.Session | None = None,
    station_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    resp = sess.get(MTA_ALERTS_JSON_URL, timeout=timeout_s)
    resp.raise_for_status()
    payload = resp.json()
    entities = payload.get("entity") or []
    matchers = list(_STATION_MATCHERS)
    for name in station_names or []:
        token = name.lower().replace("–", "-").replace("—", "-")
        matchers.append((name, [token, token.replace(" streets", ""), token.replace(" avenue", " ave")]))

    out: list[dict[str, Any]] = []
    for ent in entities:
        alert = ent.get("alert") or {}
        text = _alert_text(alert)
        if not text:
            continue
        mercury = alert.get("transit_realtime.mercury_alert") or {}
        alert_type = str(mercury.get("alert_type") or "Alert")
        text_l = text.lower().replace("–", "-").replace("—", "-")
        matched_names: list[str] = []
        for name, tokens in matchers:
            if any(tok in text_l for tok in tokens):
                matched_names.append(name)
        # Keep only alerts that hit known desk stations OR strong closure language citywide.
        access = _alert_access(alert_type, text)
        if not matched_names and access != "limited":
            continue
        if not matched_names and access == "limited":
            # Keep a thin citywide sample of limited alerts (no station pin).
            if len([a for a in out if not a.get("station_names")]) >= 25:
                continue
        out.append(
            {
                "id": f"mta:live:{ent.get('id')}",
                "label": f"MTA · {text[:140]}",
                "access": access,
                "station_names": matched_names,
                "asset_ids": [],
                "effect": alert_type.lower().replace(" ", "_"),
                "alert_type": alert_type,
            }
        )
    return out[:200]


def build_live_access_fixture(
    *,
    fixture_fallback: dict[str, Any] | None = None,
    api_key_511: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch live feeds; on total failure return fixture_fallback (or empty shell)."""
    sess = session or requests.Session()
    status: dict[str, Any] = {"fetched_at_utc": _now_iso(), "sources": {}}
    dot: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        dot = fetch_dot_speeds(session=sess)
        status["sources"]["nyc_dot_speeds"] = {"ok": True, "n": len(dot)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"dot: {exc}")
        status["sources"]["nyc_dot_speeds"] = {"ok": False, "error": str(exc)}

    try:
        events_511, meta_511 = fetch_nysdot_511_events(api_key=api_key_511, session=sess)
        status["sources"]["nysdot_511_events"] = meta_511
        if events_511:
            events = events_511
        else:
            closures = fetch_street_closures_as_511_style(session=sess)
            events = closures
            status["sources"]["nyc_street_closures"] = {
                "ok": True,
                "n": len(closures),
                "role": "511-style fallback (construction, not emergency flood closures)",
            }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"511/closures: {exc}")
        status["sources"]["nysdot_511_events"] = {"ok": False, "error": str(exc)}
        try:
            closures = fetch_street_closures_as_511_style(session=sess)
            events = closures
            status["sources"]["nyc_street_closures"] = {"ok": True, "n": len(closures)}
        except Exception as exc2:  # noqa: BLE001
            errors.append(f"closures: {exc2}")

    try:
        alerts = fetch_mta_alerts(session=sess)
        status["sources"]["mta_alerts"] = {"ok": True, "n": len(alerts)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mta: {exc}")
        status["sources"]["mta_alerts"] = {"ok": False, "error": str(exc)}

    live_ok = bool(dot or events or alerts)
    if not live_ok:
        if fixture_fallback:
            fb = dict(fixture_fallback)
            fb["live_status"] = {
                **status,
                "mode": "fixture_fallback",
                "errors": errors,
                "note": "Live feeds unavailable — using Ida research fixture",
            }
            fb.setdefault("id", "ida_access_signals_v1")
            return fb
        return {
            "id": "access_signals_live_empty",
            "replay": None,
            "honesty": "Live feeds failed; no fixture supplied.",
            "sources": [],
            "dot_speeds": [],
            "events_511": [],
            "mta_alerts": [],
            "joins": [],
            "live_status": {**status, "mode": "empty", "errors": errors},
        }

    status["sources"]["mta_bus_time_vehicles"] = dict(BUS_TIME_SKIPPED)
    return {
        "id": "access_signals_live_v1",
        "replay": None,
        "mode": "live",
        "fetched_at_utc": status["fetched_at_utc"],
        "honesty": (
            "Live/fresher open DOT speeds + 511-style closures + MTA alerts joined to "
            "research HAND depth — NOT official closures. Free-flow priors are heuristic. "
            "Bus Time vehicles skipped (no MTA_BUS_TIME_API_KEY)."
        ),
        "sources": ["nyc_dot_speeds", "nysdot_511_events", "nyc_street_closures", "mta_alerts"],
        "sources_skipped": [BUS_TIME_SKIPPED],
        "buffer_m": 120,
        "dot_speeds": dot,
        "events_511": events,
        "mta_alerts": alerts,
        "joins": [],  # geometry / name join only for live
        "live_status": {**status, "mode": "live", "errors": errors},
    }


def merge_live_over_fixture(
    live: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Prefer live rows; keep fixture explicit joins for Ida shortlist story when live empty on those ids."""
    if live.get("mode") == "fixture_fallback" or live.get("id", "").startswith("ida_"):
        return live
    merged = dict(live)
    # Preserve fixture joins so Ida shortlist chips stay demo-stable when overlaying live.
    merged["joins"] = list(fixture.get("joins") or [])
    merged["fixture_id"] = fixture.get("id")
    merged["honesty"] = (
        "Live/fresher feeds preferred; Ida fixture joins retained for shortlist replay. "
        "NOT official closures."
    )
    return merged


def write_live_fixture(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path


def nearest_slow_links(
    lon: float,
    lat: float,
    speeds: list[dict[str, Any]],
    *,
    buffer_m: float = 120.0,
) -> list[dict[str, Any]]:
    hits = []
    for sp in speeds:
        if sp.get("lon") is None or sp.get("lat") is None:
            continue
        if haversine_m(lon, lat, float(sp["lon"]), float(sp["lat"])) <= buffer_m:
            hits.append(sp)
    return hits
