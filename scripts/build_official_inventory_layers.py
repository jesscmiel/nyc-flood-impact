#!/usr/bin/env python3
"""Ingest FS-57 Tier-1 official inventory into Decision Desk (product overlays + exposure).

Sources:
  1. NYC Facilities Database ji82-xba5 → critical_facilities.geojson
  2. MTA Subway Stations 39hk-dx4f → subway_stations.geojson
  3. NYC Stormwater Flood Maps 9i7c-xyvv (ArcGIS deep/moderate current) → overlay + join flag
  4. LION 2v4z-66xt tunnels (RW_TYPE=4) → overlay + road tunnel chip
  5. Building Elevation & Subgrade BES bsin-59hv → sample near wet facilities

Rebuilds exposure GPKG + Decision Desk ranking, refreshes shortlist IDs / access joins,
and regenerates product_map.html.
NOT NWS / NOT decision-grade / NOT Ida inundation truth for stormwater planning polygons.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
from shapely.geometry import Point, mapping, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

from flood_risk.exposure.geopackage import build_exposure_gpkg  # noqa: E402
from flood_risk.risk.ranked_assets import build_ranked_assets, write_ranked_assets  # noqa: E402
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
RAW_INFRA = ROOT / "data" / "raw" / "infrastructure"
RAW_SW = ROOT / "data" / "raw" / "stormwater"
RAW_LION = ROOT / "data" / "raw" / "lion"
UA = "nyc-flood-impact/1.0 (research; official-inventory-layers)"

FAC_URL = "https://data.cityofnewyork.us/resource/ji82-xba5.json"
MTA_URL = "https://data.ny.gov/resource/39hk-dx4f.json"
BES_URL = "https://data.cityofnewyork.us/resource/bsin-59hv.json"
STORMWATER_QUERY = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "DEP_Stormwater___Moderate_with_Current_Sea_Level_Rise/FeatureServer/14/query"
)
LION_ZIP_URL = (
    "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/"
    "46245ca1-9661-4770-b38f-d2b8f23c5c82?filename=nyclion.zip"
)

# Stable shortlist targets after official inventory swap
SMITH9_GTFS = "F22"
# Brooklyn Hospital Downtown — ≥8 cm HAND + BES first-floor chip (SIUH North pin is only ~6.8 cm)
SHORTLIST_FAC_UID = "a464e8e63eb8b2c92ab1995735cfd284"
SHORTLIST_IDS = (
    f"stations:gtfs:{SMITH9_GTFS}",
    "road:25430129",
    f"facilities:uid:{SHORTLIST_FAC_UID}",
    "road:37394898",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _download(url: str, dest: Path, *, timeout: int = 600) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return len(data)


def _soda_get(url: str, params: dict[str, Any], *, timeout: int = 180) -> list[dict]:
    q = urllib.parse.urlencode(params, safe="(),'")
    full = f"{url}?{q}"
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                full,
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"SODA fetch failed after retries: {full}") from last_err


def _soda_paged(
    url: str,
    params: dict[str, Any],
    *,
    page: int = 50000,
    cache_path: Path | None = None,
) -> list[dict]:
    if cache_path is not None and cache_path.exists() and cache_path.stat().st_size > 100:
        return json.loads(cache_path.read_text())
    out: list[dict] = []
    offset = 0
    while True:
        batch_params = dict(params)
        batch_params["$limit"] = page
        batch_params["$offset"] = offset
        batch = _soda_get(url, batch_params)
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(out))
    return out


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _title_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s:
        return s
    # Keep short all-caps tokens like FDNY / NYPD
    if s.isupper() and len(s) <= 6:
        return s
    return s.title() if s.isupper() else s


def build_facilities() -> dict[str, Any]:
    where = (
        "(facsubgrp='HOSPITALS AND CLINICS' AND factype in('HOSPITAL','ACUTE CARE HOSPITAL'))"
        " OR (facsubgrp='FIRE SERVICES' AND factype='FIREHOUSE')"
        " OR (facsubgrp='POLICE SERVICES' AND factype='POLICE STATION')"
        " OR (facsubgrp='PUBLIC K-12 SCHOOLS')"
    )
    rows = _soda_paged(
        FAC_URL,
        {
            "$where": where,
            "$select": (
                "uid,facname,factype,facsubgrp,facgroup,facdomain,address,boro,"
                "latitude,longitude,opname,overagency"
            ),
        },
        cache_path=RAW_INFRA / "facilities_ji82_xba5_rows.json",
    )
    feats = []
    counts: dict[str, int] = {}
    for r in rows:
        try:
            lat = float(r["latitude"])
            lon = float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-74.3 <= lon <= -73.6 and 40.4 <= lat <= 41.0):
            continue
        factype = (r.get("factype") or "").strip()
        sub = (r.get("facsubgrp") or "").strip()
        if sub == "HOSPITALS AND CLINICS":
            ftype = "hospital"
        elif sub == "FIRE SERVICES":
            ftype = "fire"
        elif sub == "POLICE SERVICES":
            ftype = "police"
        else:
            ftype = "school"
        counts[ftype] = counts.get(ftype, 0) + 1
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "name": _title_name(r.get("facname") or "Facility"),
                    "facility_type": ftype,
                    "factype": factype,
                    "facsubgrp": sub,
                    "uid": r.get("uid") or "",
                    "address": r.get("address") or "",
                    "boro": r.get("boro") or "",
                    "source": "nyc_facilities_ji82-xba5",
                    "inventory": "official_open_data",
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": "critical_facilities",
        "properties": {
            "updated_utc": _now(),
            "source": "ji82-xba5",
            "source_label": "NYC Facilities Database",
            "n": len(feats),
            "counts": counts,
            "filters": {
                "hospitals": "HOSPITAL / ACUTE CARE HOSPITAL",
                "fire": "FIREHOUSE",
                "police": "POLICE STATION",
                "schools": "PUBLIC K-12 SCHOOLS",
            },
            "honesty": (
                "Official open inventory pins for research desk — not flood ops truth "
                "and not 'must stay open' guidance."
            ),
            "official_nws": False,
            "decision_grade": False,
        },
        "features": feats,
    }
    out = ASSETS / "critical_facilities.geojson"
    out.write_text(json.dumps(fc))
    RAW_INFRA.mkdir(parents=True, exist_ok=True)
    (RAW_INFRA / "facilities_ji82_xba5_meta.json").write_text(
        json.dumps(fc["properties"], indent=2)
    )
    return fc["properties"]


def build_mta_stations() -> dict[str, Any]:
    rows = _soda_paged(
        MTA_URL,
        {
            "$select": (
                "gtfs_stop_id,station_id,complex_id,stop_name,borough,daytime_routes,"
                "structure,ada,gtfs_latitude,gtfs_longitude,line,division"
            ),
        },
        page=5000,
        cache_path=RAW_INFRA / "mta_stations_39hk_dx4f_rows.json",
    )
    feats = []
    structure_counts: dict[str, int] = {}
    for r in rows:
        try:
            lat = float(r["gtfs_latitude"])
            lon = float(r["gtfs_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        structure = (r.get("structure") or "").strip() or "Unknown"
        structure_counts[structure] = structure_counts.get(structure, 0) + 1
        name = (r.get("stop_name") or "").strip() or (r.get("gtfs_stop_id") or "Station")
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "railway": "station",
                    "station": "subway",
                    "gtfs_stop_id": r.get("gtfs_stop_id") or "",
                    "station_id": r.get("station_id") or "",
                    "complex_id": r.get("complex_id") or "",
                    "borough": r.get("borough") or "",
                    "daytime_routes": r.get("daytime_routes") or "",
                    "structure": structure,
                    "ada": r.get("ada"),
                    "line": r.get("line") or "",
                    "division": r.get("division") or "",
                    "source": "mta_subway_stations_39hk-dx4f",
                    "inventory": "official_open_data",
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": "subway_stations",
        "properties": {
            "updated_utc": _now(),
            "source": "39hk-dx4f",
            "source_label": "MTA Subway Stations (NYS Open Data)",
            "n": len(feats),
            "structure_counts": structure_counts,
            "honesty": (
                "Official MTA stop pins — station ≠ street entrance. "
                "Structure is inventory context for research action hints."
            ),
            "official_nws": False,
        },
        "features": feats,
    }
    (ASSETS / "subway_stations.geojson").write_text(json.dumps(fc))
    RAW_INFRA.mkdir(parents=True, exist_ok=True)
    (RAW_INFRA / "mta_stations_39hk_dx4f_meta.json").write_text(
        json.dumps(
            {k: v for k, v in fc["properties"].items() if k != "honesty"},
            indent=2,
        )
    )
    return fc["properties"]


def build_stormwater_overlay() -> dict[str, Any]:
    RAW_SW.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_SW / "moderate_current_deep_raw.geojson"
    if not raw_path.exists() or raw_path.stat().st_size < 1000:
        params = urllib.parse.urlencode(
            {
                "where": "Flooding_Category=2",
                "outFields": "OBJECTID,Flooding_Category",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
            }
        )
        _download(f"{STORMWATER_QUERY}?{params}", raw_path, timeout=300)
    raw = json.loads(raw_path.read_text())
    feats_in = raw.get("features") or []
    simplified = []
    for f in feats_in:
        geom = shape(f["geometry"])
        # ~25 m tolerance in degrees at NYC latitude
        geom_s = geom.simplify(0.00025, preserve_topology=True)
        if geom_s.is_empty:
            continue
        simplified.append(
            {
                "type": "Feature",
                "properties": {
                    "flooding_category": 2,
                    "flooding_label": "Deep and Contiguous Flooding (≥1 ft planning)",
                    "scenario": "moderate_flood_current_sea_level",
                    "source": "nyc_stormwater_9i7c-xyvv",
                    "role": "city_pluvial_planning_polygon",
                },
                "geometry": mapping(geom_s),
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": "stormwater_deep_moderate_current",
        "properties": {
            "updated_utc": _now(),
            "source": "9i7c-xyvv",
            "scenario": "Moderate Flood with Current Sea Levels",
            "flooding_category": 2,
            "n_features": len(simplified),
            "honesty": (
                "City stormwater planning polygons — NOT event-specific Ida depth. "
                "Assumes functioning drains + uniform rain. Research join only."
            ),
            "official_nws": False,
            "ida_depth": False,
        },
        "features": simplified,
    }
    out = ASSETS / "stormwater_deep_moderate_current.geojson"
    out.write_text(json.dumps(fc))
    meta = {
        "updated_utc": fc["properties"]["updated_utc"],
        "product_asset": out.name,
        "n_features": len(simplified),
        "raw_bytes": raw_path.stat().st_size,
        "product_bytes": out.stat().st_size,
        "scenario": fc["properties"]["scenario"],
        "source": "9i7c-xyvv",
    }
    (ASSETS / "stormwater_deep_moderate_current_meta.json").write_text(
        json.dumps(meta, indent=2)
    )
    return meta


def build_lion_tunnels() -> dict[str, Any]:
    RAW_LION.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_LION / "nyclion.zip"
    if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
        print(f"fetch LION zip → {zip_path}")
        _download(LION_ZIP_URL, zip_path, timeout=900)
    extract_dir = RAW_LION / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    if not any(extract_dir.rglob("*.gdb")) and not any(extract_dir.rglob("*.shp")):
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

    gdb = next(extract_dir.rglob("*.gdb"), None)
    if gdb is None:
        raise RuntimeError("LION extract missing .gdb")
    layers_df = gpd.list_layers(gdb)
    layer_names = list(layers_df["name"].astype(str))
    # Prefer classic LION street centerline layer
    prefer = [n for n in layer_names if n.lower() in ("lion", "lion_street", "street")]
    layer = prefer[0] if prefer else layer_names[0]
    gdf = gpd.read_file(gdb, layer=layer)
    # Normalize RW_TYPE column
    rw_col = None
    for c in gdf.columns:
        if c.upper() == "RW_TYPE":
            rw_col = c
            break
    if rw_col is None:
        raise RuntimeError(f"RW_TYPE missing in LION layer {layer}; cols={list(gdf.columns)[:40]}")
    # 3=bridge, 4=tunnel per DCP LION dictionary
    rw_norm = gdf[rw_col].map(lambda v: str(v).strip().split(".")[0] if v == v else "")
    tun = gdf[rw_norm.isin(["4"])].copy()
    if tun.crs is None:
        tun = tun.set_crs(2263)  # NY State Plane LI ft — LION default
    tun = tun.to_crs(4326)

    name_col = next((c for c in ("Street", "street", "ST_NAME", "Full_Street_Name") if c in tun.columns), None)
    feats = []
    for idx, row in tun.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        props = {
            "name": str(row[name_col]) if name_col else f"LION tunnel {idx}",
            "rw_type": 4,
            "rw_label": "tunnel",
            "source": "lion_2v4z-66xt",
            "role": "tunnel_underpass_inventory",
        }
        # Keep a couple of useful ids if present
        for key in ("SegmentID", "segmentid", "StreetCode", "FeatureTyp"):
            if key in tun.columns and row.get(key) == row.get(key):
                props[key.lower()] = str(row.get(key))
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(geom),
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": "lion_tunnels",
        "properties": {
            "updated_utc": _now(),
            "source": "2v4z-66xt",
            "layer": layer,
            "rw_type": 4,
            "n": len(feats),
            "honesty": (
                "LION tunnel / underpass centerlines — inventory only, not live closures."
            ),
            "official_nws": False,
        },
        "features": feats,
    }
    out = ASSETS / "lion_tunnels.geojson"
    out.write_text(json.dumps(fc))
    meta = {
        "updated_utc": fc["properties"]["updated_utc"],
        "product_asset": out.name,
        "n": len(feats),
        "layer": layer,
        "source": "2v4z-66xt",
    }
    (ASSETS / "lion_tunnels_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def build_bes_sample(anchors: list[tuple[float, float]], *, radius_m: float = 350.0, max_n: int = 400) -> dict[str, Any]:
    """Pull BES points near wet-facility / shortlist anchors via SODA within_circle."""
    seen: set[str] = set()
    feats: list[dict] = []
    for lon, lat in anchors:
        where = f"within_circle(the_geom,{lat},{lon},{int(radius_m)})"
        try:
            rows = _soda_get(
                BES_URL,
                {
                    "$where": where,
                    "$limit": 80,
                    "$select": (
                        "bin,bbl,address,z_grade,z_floor,subgrade,latitude,longitude,borough,notes1"
                    ),
                },
                timeout=120,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"BES query failed near {lat},{lon}: {exc}")
            continue
        for r in rows:
            key = str(r.get("bin") or r.get("bbl") or f"{r.get('latitude')},{r.get('longitude')}")
            if key in seen:
                continue
            try:
                plat = float(r["latitude"])
                plon = float(r["longitude"])
                z_grade = float(r["z_grade"]) if r.get("z_grade") not in (None, "") else None
                z_floor = float(r["z_floor"]) if r.get("z_floor") not in (None, "") else None
            except (KeyError, TypeError, ValueError):
                continue
            seen.add(key)
            sub = (r.get("subgrade") or "").strip().upper()
            feats.append(
                {
                    "type": "Feature",
                    "properties": {
                        "bin": r.get("bin"),
                        "bbl": r.get("bbl"),
                        "address": r.get("address") or "",
                        "z_grade_ft_navd88": z_grade,
                        "z_floor_ft_navd88": z_floor,
                        "subgrade": sub,
                        "subgrade_present": sub == "Y",
                        "borough": r.get("borough") or "",
                        "notes1": r.get("notes1") or "",
                        "source": "bes_bsin-59hv",
                        "role": "elevation_subgrade_sample",
                    },
                    "geometry": {"type": "Point", "coordinates": [plon, plat]},
                }
            )
            if len(feats) >= max_n:
                break
        if len(feats) >= max_n:
            break
    fc = {
        "type": "FeatureCollection",
        "name": "bes_near_wet_facilities",
        "properties": {
            "updated_utc": _now(),
            "source": "bsin-59hv",
            "n": len(feats),
            "radius_m": radius_m,
            "honesty": (
                "BES street-view LiDAR elevations (NAVD88) near wet facilities — "
                "not a basement inventory; do not mix casually with HAND cm."
            ),
            "official_nws": False,
        },
        "features": feats,
    }
    out = ASSETS / "bes_near_wet_facilities.geojson"
    out.write_text(json.dumps(fc))
    meta = {
        "updated_utc": fc["properties"]["updated_utc"],
        "product_asset": out.name,
        "n": len(feats),
        "source": "bsin-59hv",
        "radius_m": radius_m,
    }
    (ASSETS / "bes_near_wet_facilities_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def rebuild_exposure() -> dict[str, Any]:
    roads = ASSETS / "roads.geojson"
    stations = ASSETS / "subway_stations.geojson"
    facilities = ASSETS / "critical_facilities.geojson"
    gpkg = ASSETS / "exposure_citywide.gpkg"
    meta = build_exposure_gpkg(
        roads_geojson=roads,
        stations_geojson=stations,
        facilities_geojson=facilities,
        out_gpkg=gpkg,
    )
    meta["inventory"] = {
        "facilities": "ji82-xba5",
        "stations": "39hk-dx4f",
        "roads": "osm",
    }
    (ASSETS / "exposure_citywide.json").write_text(json.dumps(meta, indent=2))
    (OUTPUTS_DIR / "exposure_citywide.json").write_text(json.dumps(meta, indent=2))
    return meta


def rebuild_desk() -> dict[str, Any]:
    gpkg = ASSETS / "exposure_citywide.gpkg"
    depth = PROCESSED_DIR / "inundation" / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not depth.exists():
        depth = PROCESSED_DIR / "inundation" / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    lead_tifs: list[tuple[float, Path]] = []
    for lead in range(0, 37, 3):
        for stem in (
            f"depth_metro_mrms_cum_lead_{lead:02d}h_m.tif",
            f"depth_mrms_cum_lead_{lead:02d}h_m.tif",
        ):
            path = PROCESSED_DIR / "inundation" / stem
            if path.exists():
                lead_tifs.append((float(lead), path))
                break
    access_fixture = ASSETS / "access_signals_ida_fixture.json"
    payload = build_ranked_assets(
        gpkg=gpkg,
        depth_tif=depth,
        lead_tifs=lead_tifs,
        top_n=None,
        access_fixture=access_fixture if access_fixture.exists() else None,
    )
    return payload


def enrich_inventory_joins(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach stormwater / LION tunnel / BES / MTA structure chips onto wet assets."""
    sw_path = ASSETS / "stormwater_deep_moderate_current.geojson"
    lion_path = ASSETS / "lion_tunnels.geojson"
    bes_path = ASSETS / "bes_near_wet_facilities.geojson"
    stations_path = ASSETS / "subway_stations.geojson"

    sw_geoms = []
    if sw_path.exists():
        sw = json.loads(sw_path.read_text())
        sw_geoms = [shape(f["geometry"]) for f in (sw.get("features") or []) if f.get("geometry")]
    sw_union = unary_union(sw_geoms) if sw_geoms else None

    lion_geoms = []
    lion_names: list[str] = []
    if lion_path.exists():
        lion = json.loads(lion_path.read_text())
        for f in lion.get("features") or []:
            if not f.get("geometry"):
                continue
            lion_geoms.append(shape(f["geometry"]))
            lion_names.append(str((f.get("properties") or {}).get("name") or "tunnel"))
    lion_tree = STRtree(lion_geoms) if lion_geoms else None

    bes_pts: list[tuple[float, float, dict]] = []
    if bes_path.exists():
        bes = json.loads(bes_path.read_text())
        for f in bes.get("features") or []:
            p = f.get("properties") or {}
            coords = (f.get("geometry") or {}).get("coordinates") or []
            if len(coords) >= 2:
                bes_pts.append((float(coords[0]), float(coords[1]), p))

    structure_by_gtfs: dict[str, str] = {}
    if stations_path.exists():
        st = json.loads(stations_path.read_text())
        for f in st.get("features") or []:
            p = f.get("properties") or {}
            gid = str(p.get("gtfs_stop_id") or "")
            if gid:
                structure_by_gtfs[gid] = str(p.get("structure") or "")

    n_sw = n_lion = n_bes = n_struct = 0
    for a in payload.get("assets") or []:
        lon, lat = a.get("lon"), a.get("lat")
        pt = Point(float(lon), float(lat)) if lon is not None and lat is not None else None

        # MTA structure
        aid = str(a.get("id") or "")
        if a.get("asset_type") == "station":
            gtfs = None
            if aid.startswith("stations:gtfs:"):
                gtfs = aid.split(":", 2)[-1]
            structure = structure_by_gtfs.get(gtfs or "", a.get("structure") or "")
            if structure:
                a["structure"] = structure
                n_struct += 1
                if structure.lower() in ("subway", "underground", "open cut", "open-cut"):
                    hint = a.get("action_hint") or ""
                    a["action_hint"] = (
                        f"{hint} Structure={structure} (inventory) — entrance access may differ."
                    ).strip()

        # Stormwater deep zone join
        a["in_city_stormwater_deep_zone"] = False
        if pt is not None and sw_union is not None and sw_union.contains(pt):
            a["in_city_stormwater_deep_zone"] = True
            a["stormwater_chip"] = "in city stormwater deep zone (research join)"
            n_sw += 1

        # LION tunnel proximity for roads
        a["near_lion_tunnel"] = False
        if pt is not None and lion_tree is not None and a.get("asset_type") == "road":
            # Buffer ~40 m in degrees
            buf = pt.buffer(0.0004)
            idxs = lion_tree.query(buf)
            if len(idxs):
                # pick nearest
                best_i = None
                best_d = 1e9
                for i in idxs:
                    d = lion_geoms[int(i)].distance(pt)
                    if d < best_d:
                        best_d = d
                        best_i = int(i)
                if best_i is not None and best_d <= 0.00045:
                    a["near_lion_tunnel"] = True
                    a["lion_tunnel_name"] = lion_names[best_i]
                    a["lion_chip"] = f"LION tunnel/underpass nearby · {lion_names[best_i]}"
                    n_lion += 1

        # BES nearest for facilities
        if a.get("asset_type") == "facility" and lon is not None and lat is not None and bes_pts:
            best = None
            best_d = 1e9
            for blon, blat, bp in bes_pts:
                d = _haversine_m(float(lon), float(lat), blon, blat)
                if d < best_d:
                    best_d = d
                    best = bp
            if best is not None and best_d <= 120.0:
                a["bes_near_m"] = round(best_d, 1)
                a["bes_subgrade"] = best.get("subgrade")
                a["bes_z_floor_ft"] = best.get("z_floor_ft_navd88")
                a["bes_z_grade_ft"] = best.get("z_grade_ft_navd88")
                if best.get("subgrade_present"):
                    a["bes_chip"] = "subgrade present (BES research join)"
                elif best.get("z_floor_ft_navd88") is not None:
                    a["bes_chip"] = (
                        f"first-floor ~{best['z_floor_ft_navd88']:.1f} ft NAVD88 (BES)"
                    )
                n_bes += 1

    payload["official_inventory_joins"] = {
        "stormwater_deep_hits": n_sw,
        "lion_tunnel_road_hits": n_lion,
        "bes_facility_hits": n_bes,
        "station_structure_hits": n_struct,
        "honesty": (
            "Research joins only — stormwater planning ≠ Ida HAND; "
            "BES NAVD88 ≠ HAND cm; LION tunnels ≠ live closures."
        ),
    }
    # Refresh honesty line
    payload["honesty"] = (
        "Ranked wet assets from research inundation × official open inventory "
        "(Facilities DB / MTA stations) + OSM roads. "
        "Stations/facilities use max HAND depth within 250 m of the pin. "
        "NOT official NWS thresholds. NOT decision-grade infrastructure guidance."
    )
    return payload


def update_access_fixture_shortlist() -> None:
    path = ASSETS / "access_signals_ida_fixture.json"
    if not path.exists():
        return
    fix = json.loads(path.read_text())
    new_station = f"stations:gtfs:{SMITH9_GTFS}"
    new_fac = f"facilities:uid:{SHORTLIST_FAC_UID}"
    legacy_fac = {
        "facilities:40:Staten Island University Hospital",
        "facilities:uid:2e5ef01c1110cceaa57585d5d4e340a6",  # SIUH North
        new_fac,
    }
    for al in fix.get("mta_alerts") or []:
        if al.get("id") == "mta:smith9_suspend":
            al["station_names"] = ["Smith-9 Sts", "Smith–9th Streets", "Smith-9th Streets"]
            al["asset_ids"] = [new_station]
    for j in fix.get("joins") or []:
        aid = str(j.get("asset_id") or "")
        if aid in (
            "stations:194:Smith–9th Streets",
            new_station,
        ) or "Smith" in aid:
            j["asset_id"] = new_station
        elif aid in legacy_fac or aid.startswith("facilities:40:") or "Staten Island University Hospital" in aid:
            j["asset_id"] = new_fac
    path.write_text(json.dumps(fix, indent=2) + "\n")


def patch_shortlist_constants() -> None:
    """No-op when product_map_html / curation already pin stable gtfs/uid IDs."""
    return


def update_manifest(payload: dict[str, Any], metas: dict[str, Any]) -> None:
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        manifest = json.loads(mp.read_text())
        desk = manifest.setdefault("asset_decision_desk", {})
        desk["assets_json"] = "decision_desk_assets.json"
        desk["assets_geojson"] = "decision_desk_assets.geojson"
        desk["shortlist_ids"] = list(SHORTLIST_IDS)
        desk["inventory"] = {
            "facilities": "ji82-xba5",
            "stations": "39hk-dx4f",
            "stormwater": "9i7c-xyvv",
            "lion_tunnels": "2v4z-66xt",
            "bes": "bsin-59hv",
        }
        manifest["exposure"] = {
            "gpkg": "exposure_citywide.gpkg",
            "meta": "exposure_citywide.json",
            "layers": ["roads", "stations", "facilities"],
            "inventory": desk["inventory"],
            "official": False,
        }
        manifest["official_inventory_layers"] = {
            "facilities_geojson": "critical_facilities.geojson",
            "stations_geojson": "subway_stations.geojson",
            "stormwater_geojson": "stormwater_deep_moderate_current.geojson",
            "lion_tunnels_geojson": "lion_tunnels.geojson",
            "bes_geojson": "bes_near_wet_facilities.geojson",
            "metas": metas,
            "joins": payload.get("official_inventory_joins"),
            "honesty": (
                "Official open inventory + planning overlays for Decision Desk. "
                "NOT NWS / NOT decision-grade / stormwater ≠ Ida depth."
            ),
        }
        manifest["infra"] = {
            **(manifest.get("infra") or {}),
            "roads_geojson": "roads.geojson",
            "stations_geojson": "subway_stations.geojson",
            "facilities_geojson": "critical_facilities.geojson",
        }
        mp.write_text(json.dumps(manifest, indent=2))


def regenerate_html() -> Path | None:
    try:
        from product_map_html import write_product_html
    except Exception as exc:  # noqa: BLE001
        print(f"html regen skipped: {exc}")
        return None
    manifest = json.loads((ASSETS / "product_manifest.json").read_text())
    pluvial = (
        json.loads((ASSETS / "pluvial_meta.json").read_text())
        if (ASSETS / "pluvial_meta.json").exists()
        else {}
    )
    validation = (
        json.loads((ASSETS / "validation_product.json").read_text())
        if (ASSETS / "validation_product.json").exists()
        else {}
    )
    return write_product_html(manifest, pluvial, validation)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    print("1/7 Facilities DB…")
    fac_meta = build_facilities()
    print(json.dumps(fac_meta, indent=2))

    print("2/7 MTA stations…")
    sta_meta = build_mta_stations()
    print(json.dumps(sta_meta, indent=2))

    print("3/7 Stormwater deep overlay…")
    sw_meta = build_stormwater_overlay()
    print(json.dumps(sw_meta, indent=2))

    print("4/7 LION tunnels…")
    lion_meta = build_lion_tunnels()
    print(json.dumps(lion_meta, indent=2))

    print("5/7 Exposure GPKG…")
    exp_meta = rebuild_exposure()
    print(json.dumps(exp_meta["layers"], indent=2))

    print("6/7 Decision Desk rebuild…")
    update_access_fixture_shortlist()
    patch_shortlist_constants()
    payload = rebuild_desk()

    # BES anchors = wet facilities + shortlist coords
    anchors: list[tuple[float, float]] = [
        (-73.995959, 40.67358),  # Smith-9
        (-73.8371, 40.7401),  # Van Wyck
        (-74.086048225, 40.5847678934),  # SIUH North
        (-73.98045, 40.69354),  # Myrtle
    ]
    for a in payload.get("assets") or []:
        if a.get("asset_type") == "facility" and a.get("lon") is not None:
            anchors.append((float(a["lon"]), float(a["lat"])))
            if len(anchors) >= 40:
                break
    print("6b/7 BES sample…")
    bes_meta = build_bes_sample(anchors)
    print(json.dumps(bes_meta, indent=2))

    payload = enrich_inventory_joins(payload)
    out_json = ASSETS / "decision_desk_assets.json"
    out_geo = ASSETS / "decision_desk_assets.geojson"
    write_ranked_assets(payload, out_json, out_geo)
    (OUTPUTS_DIR / "decision_desk_assets.json").write_text(out_json.read_text())

    metas = {
        "facilities": fac_meta,
        "stations": sta_meta,
        "stormwater": sw_meta,
        "lion": lion_meta,
        "bes": bes_meta,
        "exposure": exp_meta.get("layers"),
        "desk_counts": payload.get("counts"),
        "joins": payload.get("official_inventory_joins"),
        "shortlist_ids": list(SHORTLIST_IDS),
    }
    (ASSETS / "official_inventory_layers_meta.json").write_text(json.dumps(metas, indent=2))
    update_manifest(payload, metas)

    print("7/7 product_map.html…")
    html = regenerate_html()
    print(json.dumps({"html": str(html) if html else None, "shortlist": list(SHORTLIST_IDS), "counts": payload.get("counts"), "joins": payload.get("official_inventory_joins")}, indent=2))


if __name__ == "__main__":
    main()
