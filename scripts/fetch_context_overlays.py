#!/usr/bin/env python3
"""Fetch static FEMA NFHL + NOAA river-gauge context overlays (not event inundation)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nyc_flash_flood_case_study.extents import EXTENTS

PROJECT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT / "data" / "raw" / "context"
ASSETS = PROJECT / "figures" / "product_assets"

FEMA_URL = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/"
    "USA_Flood_Hazard_Reduced_Set_gdb/FeatureServer/0/query"
)
# NOAA Event-Driven river gauges (AHPS) — NWM-adjacent observed context, not NWM channel RT.
GAUGE_URL = (
    "https://mapservices.weather.noaa.gov/eventdriven/rest/services/water/riv_gauges/MapServer/0/query"
)


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={"User-Agent": "nyc-flood-impact/0.1"})
    with urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_fema(extent_id: str = "south_queens") -> Path:
    b = EXTENTS[extent_id]["bounds"]
    # Pad slightly so shoreline SFHA polygons are included.
    geom = f"{b['xmin']-0.02},{b['ymin']-0.02},{b['xmax']+0.02},{b['ymax']+0.02}"
    data = _get_json(
        FEMA_URL,
        {
            "where": "1=1",
            "geometry": geom,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": "5000",
        },
    )
    if data.get("type") != "FeatureCollection":
        raise RuntimeError(f"Unexpected FEMA response: {str(data)[:400]}")
    out = OUT_DIR / f"fema_nfhl_{extent_id}.geojson"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "label": "FEMA NFHL flood hazard zones (static)",
        "disclaimer": (
            "Regulatory / static flood-hazard context from FEMA NFHL-derived layers. "
            "Not event inundation, not a live forecast, not SWMM depths."
        ),
        "source": FEMA_URL,
        "extent_id": extent_id,
        "n_features": len(data.get("features", [])),
    }
    data["properties"] = {**(data.get("properties") or {}), **meta}
    out.write_text(json.dumps(data))
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "fema_nfhl.geojson").write_text(json.dumps(data))
    (ASSETS / "fema_nfhl_meta.json").write_text(json.dumps(meta, indent=2))
    return out


def fetch_nwm_context(extent_id: str = "citywide") -> Path:
    """Fetch NOAA river gauges as NWM-adjacent observed context.

    Full NWM channel routing grids are large and time-varying; gauges provide an
    honest lightweight context overlay without implying street inundation.
    """
    b = EXTENTS[extent_id]["bounds"]
    geom = f"{b['xmin']},{b['ymin']},{b['xmax']},{b['ymax']}"
    data = _get_json(
        GAUGE_URL,
        {
            "where": "1=1",
            "geometry": geom,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": "1000",
        },
    )
    if data.get("type") != "FeatureCollection":
        raise RuntimeError(f"Unexpected gauge response: {str(data)[:400]}")
    out = OUT_DIR / f"nwm_ahps_gauges_{extent_id}.geojson"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "label": "NOAA AHPS river gauges (NWM-adjacent context)",
        "disclaimer": (
            "Observed/forecast river-gauge points from NOAA services. "
            "Context only — not National Water Model channel inundation and not street flooding."
        ),
        "source": GAUGE_URL,
        "nwm_note": (
            "Full NWM land-surface/channel grids not ingested this pass; gauges are the "
            "lightweight NWM-adjacent overlay."
        ),
        "extent_id": extent_id,
        "n_features": len(data.get("features", [])),
    }
    data["properties"] = {**(data.get("properties") or {}), **meta}
    out.write_text(json.dumps(data))
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "nwm_ahps_gauges.geojson").write_text(json.dumps(data))
    (ASSETS / "nwm_context_meta.json").write_text(json.dumps(meta, indent=2))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extent", default="south_queens")
    args = parser.parse_args()
    fema = fetch_fema(args.extent)
    gauges = fetch_nwm_context("citywide")
    print(f"FEMA: {fema}")
    print(f"Gauges: {gauges}")


if __name__ == "__main__":
    main()
