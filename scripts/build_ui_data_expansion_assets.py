#!/usr/bin/env python3
"""Build optional UI/data-expansion product assets (FS-56).

Writes slim open-data overlays used by Decision Desk Advanced toggles:
  - floodnet_later_events.geojson (+ meta)
  - dep_catch_basins_sample.geojson
  - building_footprints_sample.geojson (+ meta)
  - access_signals_511_archive.json / archived_511_events.geojson

Also refreshes FloodNet Open Data CSVs when missing.
Does not rescale primary HAND depth.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.validate.floodnet import (  # noqa: E402
    IDA_END_UTC,
    IDA_INIT_UTC,
    INCH_TO_M,
    parse_floodnet_gmt,
)

RAW_FN = ROOT / "data" / "raw" / "floodnet"
PROC_FN = ROOT / "data" / "processed" / "floodnet"
ASSETS = ROOT / "figures" / "product_assets"
INFRA = ROOT / "data" / "raw" / "infrastructure"
UA = "nyc-flood-impact/1.0 (research; FS-56 ui-data-expansion)"
EVENTS_URL = "https://data.cityofnewyork.us/api/views/aq7i-eu5q/rows.csv?accessType=DOWNLOAD"
META_URL = "https://data.cityofnewyork.us/api/views/kb2e-tjy3/rows.csv?accessType=DOWNLOAD"
BUILDINGS_DS = "5zhs-2jue"


def _download(url: str, dest: Path, *, timeout: int = 180) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return len(data)


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ensure_floodnet_csvs() -> None:
    RAW_FN.mkdir(parents=True, exist_ok=True)
    events = RAW_FN / "floodnet_flooding_events.csv"
    meta = RAW_FN / "floodnet_sensor_metadata.csv"
    if not events.exists() or events.stat().st_size < 1000:
        print(f"fetch FloodNet events → {events}")
        _download(EVENTS_URL, events)
    if not meta.exists() or meta.stat().st_size < 1000:
        print(f"fetch FloodNet metadata → {meta}")
        _download(META_URL, meta)


def build_floodnet_later_events() -> dict:
    ensure_floodnet_csvs()
    meta_by_id: dict[str, dict] = {}
    with (RAW_FN / "floodnet_sensor_metadata.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("Sensor ID") or "").strip()
            if not sid:
                continue
            try:
                lat = float(row["Latitude"])
                lon = float(row["Longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            meta_by_id[sid] = {
                "sensor_id": sid,
                "sensor_name": row.get("Sensor Name") or sid,
                "borough": row.get("Borough") or "",
                "lat": lat,
                "lon": lon,
            }

    later_feats: list[dict] = []
    ida_n = 0
    year_counts: Counter[int] = Counter()
    with (RAW_FN / "floodnet_flooding_events.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("Sensor ID") or "").strip()
            try:
                start = parse_floodnet_gmt(row["Flood Start Datetime (GMT)"])
            except Exception:  # noqa: BLE001
                continue
            year_counts[start.year] += 1
            if IDA_INIT_UTC <= start <= IDA_END_UTC:
                ida_n += 1
                continue
            if start <= IDA_END_UTC:
                continue
            meta = meta_by_id.get(sid)
            if not meta:
                continue
            try:
                depth_in = float(row["Maximum Flood Depth (inches)"])
            except (KeyError, TypeError, ValueError):
                depth_in = None
            props = {
                "sensor_id": sid,
                "sensor_name": row.get("Sensor Name") or meta["sensor_name"],
                "borough": meta["borough"],
                "flood_start_utc": start.isoformat().replace("+00:00", "Z"),
                "max_depth_in": depth_in,
                "max_depth_m": (depth_in * INCH_TO_M) if depth_in is not None else None,
                "source": "nyc_open_data_aq7i-eu5q",
            }
            later_feats.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [meta["lon"], meta["lat"]],
                    },
                    "properties": props,
                }
            )

    counts = Counter(f["properties"]["sensor_id"] for f in later_feats)
    by_sensor: dict[str, dict] = {}
    for feat in later_feats:
        sid = feat["properties"]["sensor_id"]
        cur = by_sensor.get(sid)
        if cur is None or (feat["properties"].get("max_depth_m") or 0) > (
            cur["properties"].get("max_depth_m") or 0
        ):
            by_sensor[sid] = feat

    agg = []
    for sid, feat in by_sensor.items():
        props = dict(feat["properties"])
        props["n_events_post_ida"] = counts[sid]
        props["role"] = "floodnet_later_events_peak"
        agg.append({"type": "Feature", "geometry": feat["geometry"], "properties": props})

    fc = {
        "type": "FeatureCollection",
        "name": "floodnet_later_events",
        "properties": {
            "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_events": len(later_feats),
            "n_sensors": len(agg),
            "ida_window_events": ida_n,
            "years": dict(year_counts),
            "honesty": (
                "Research FloodNet archive — not NWS / not decision-grade. "
                "Later events are post-Ida Open Data floods."
            ),
            "official_nws": False,
        },
        "features": sorted(agg, key=lambda f: -(f["properties"].get("max_depth_m") or 0)),
    }
    PROC_FN.mkdir(parents=True, exist_ok=True)
    (ASSETS / "floodnet_later_events.geojson").write_text(json.dumps(fc))
    (PROC_FN / "floodnet_later_events.geojson").write_text(json.dumps(fc, indent=2))
    meta = {
        "updated_utc": fc["properties"]["updated_utc"],
        "n_events_post_ida": len(later_feats),
        "n_sensors_post_ida": len(agg),
        "ida_window_events": ida_n,
        "years": dict(year_counts),
        "product_asset": "floodnet_later_events.geojson",
    }
    (ASSETS / "floodnet_later_events_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def build_dep_sample() -> dict:
    anchors = [
        (-73.9958, 40.6736),
        (-73.8371, 40.7401),
        (-74.0750, 40.5850),
        (-73.9120, 40.6930),
    ]
    csv_path = INFRA / "nycdep_catch_basins_metro.csv"
    feats: list[dict] = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
            for i, row in enumerate(csv.DictReader(f)):
                try:
                    lon = float(row["LONGITUDE"])
                    lat = float(row["LATITUDE"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not any(_haversine_m(lon, lat, a[0], a[1]) < 1200 for a in anchors):
                    continue
                unitid = row.get("UNITID") or f"CB{i}"
                feats.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": {
                            "node_id": f"dep_{unitid}",
                            "unitid": unitid,
                            "source": "nyc_open_data_catch_basin_2w2g-fk3i",
                            "kind": "catch_basin",
                            "attributes_open": True,
                        },
                    }
                )
                if len(feats) >= 800:
                    break
    fc = {
        "type": "FeatureCollection",
        "name": "dep_catch_basins_shortlist_sample",
        "properties": {
            "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_features": len(feats),
            "buffer_m": 1200,
            "honesty": (
                "Open NYC DEP catch-basin inventory sample near demo shortlist — "
                "NOT sewer performance / NOT SWMM."
            ),
            "available": len(feats) > 0,
            "official_nws": False,
        },
        "features": feats,
    }
    (ASSETS / "dep_catch_basins_sample.geojson").write_text(json.dumps(fc))
    return {"n_features": len(feats), "available": len(feats) > 0}


def build_511_archive() -> dict:
    live_path = ASSETS / "access_signals_live.json"
    fx_path = ASSETS / "access_signals_ida_fixture.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else {}
    fx = json.loads(fx_path.read_text()) if fx_path.exists() else {}
    archive = {
        "id": "access_signals_511_archive_v1",
        "role": "archived_511_style",
        "honesty": (
            "Archived 511-style / street-closure research overlay — "
            "NOT official emergency flood closures."
        ),
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixture_events_511": fx.get("events_511") or [],
        "events_511": (live.get("events_511") or [])[:60],
        "sources": {
            "ida_fixture": "access_signals_ida_fixture.json",
            "live_snapshot": "access_signals_live.json",
        },
    }
    (ASSETS / "access_signals_511_archive.json").write_text(json.dumps(archive, indent=2))
    seen: set[str] = set()
    feats: list[dict] = []
    for e in list(archive["fixture_events_511"]) + list(archive["events_511"]):
        eid = str(e.get("id") or "")
        if not eid or eid in seen:
            continue
        if e.get("lon") is None or e.get("lat") is None:
            continue
        seen.add(eid)
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
                "properties": {**e, "archived": True},
            }
        )
        if len(feats) >= 80:
            break
    fc = {
        "type": "FeatureCollection",
        "name": "archived_511_events",
        "properties": {"n": len(feats), "honesty": archive["honesty"]},
        "features": feats,
    }
    (ASSETS / "archived_511_events.geojson").write_text(json.dumps(fc))
    return {"n_features": len(feats)}


def build_building_sample() -> dict:
    boxes = [
        (-74.005, 40.668, -73.985, 40.680),
        (-73.845, 40.733, -73.828, 40.748),
    ]
    all_b: list[dict] = []
    for xmin, ymin, xmax, ymax in boxes:
        url = (
            f"https://data.cityofnewyork.us/resource/{BUILDINGS_DS}.geojson?$limit=100"
            f"&$where=within_box(the_geom,{ymax},{xmin},{ymin},{xmax})"
        )
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            for f in data.get("features") or []:
                props = dict(list((f.get("properties") or {}).items())[:12])
                props["source"] = f"nyc_open_data_{BUILDINGS_DS}"
                props["role"] = "archived_open_footprint_sample"
                all_b.append(
                    {"type": "Feature", "geometry": f.get("geometry"), "properties": props}
                )
        except Exception as exc:  # noqa: BLE001
            print(f"building fetch skipped: {type(exc).__name__}: {exc}")
    props = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_features": len(all_b),
        "honesty": (
            "Open NYC building sample — context only, not flood depths / not decision-grade."
        ),
        "official_nws": False,
        "available": len(all_b) > 0,
        "dataset": BUILDINGS_DS,
    }
    fc = {
        "type": "FeatureCollection",
        "name": "building_footprints_sample",
        "properties": props,
        "features": all_b,
    }
    (ASSETS / "building_footprints_sample.geojson").write_text(json.dumps(fc))
    (ASSETS / "building_footprints_meta.json").write_text(json.dumps(props, indent=2))
    return props


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = {
        "floodnet_later": build_floodnet_later_events(),
        "dep_sample": build_dep_sample(),
        "archive_511": build_511_archive(),
        "buildings": build_building_sample(),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
