"""Ranked wet-asset desk for Ida research replay.

Primary depth engine: MRMS QPE → pysheds HAND/bathtub (citywide).
Queens SFINCS is labeled alternate — not equally authoritative.
NOT official NWS. NOT decision-grade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio

from flood_risk.exposure.geopackage import (
    LAYER_FACILITIES,
    LAYER_ROADS,
    LAYER_STATIONS,
    line_max_depth,
    point_nearby_max_depth,
)
from flood_risk.risk.access_signals import apply_access_and_demotion, load_access_fixture
from flood_risk.risk.depth_asset_tables import DEPTH_BANDS

# Research action hints — unofficial placeholders only
BAND_ACTION_HINTS = {
    "ponding": "Screen corridor / facility for ponding; research ≥3 cm — not an SOP trigger.",
    "deep_ponding": "Elevated research depth ≥8 cm — review access / staging (unofficial).",
    "hazard": "Research depth ≥15 cm — flag for follow-up; NOT agency closure criteria.",
}

BAND_LABEL_SHORT = {
    "ponding": "≥3 cm",
    "deep_ponding": "≥8 cm",
    "hazard": "≥15 cm",
}


def _band_id(depth_m: float) -> str | None:
    if not np.isfinite(depth_m) or depth_m < DEPTH_BANDS[0]["min_m"]:
        return None
    for b in reversed(DEPTH_BANDS):
        lo, hi = b["min_m"], b["max_m"]
        if depth_m >= lo and (hi is None or depth_m < hi):
            return b["id"]
        if hi is None and depth_m >= lo:
            return b["id"]
    return None


def _band_min(band_id: str) -> float:
    for b in DEPTH_BANDS:
        if b["id"] == band_id:
            return float(b["min_m"])
    return 0.03


def _asset_name(row: Any, layer: str, idx: int) -> str:
    name = row.get("name") if hasattr(row, "get") else getattr(row, "name", None)
    if name is None or (isinstance(name, float) and np.isnan(name)) or str(name).strip() in ("", "nan", "None"):
        if layer == LAYER_ROADS:
            hwy = row.get("highway") if hasattr(row, "get") else getattr(row, "highway", None)
            osm = row.get("osm_id") if hasattr(row, "get") else getattr(row, "osm_id", None)
            return f"unnamed {hwy or 'road'} ({osm or idx})"
        return f"{layer[:-1] if layer.endswith('s') else layer} {idx}"
    return str(name)


def _asset_id(row: Any, layer: str, idx: int) -> str:
    if layer == LAYER_ROADS:
        osm = row.get("osm_id") if hasattr(row, "get") else getattr(row, "osm_id", None)
        if osm is not None and str(osm) not in ("", "nan", "None"):
            return f"road:{osm}"
    name = _asset_name(row, layer, idx)
    return f"{layer}:{idx}:{name}"


def _centroid_lonlat(geom) -> tuple[float, float] | None:
    if geom is None or geom.is_empty:
        return None
    c = geom.centroid
    return float(c.x), float(c.y)


POINT_NEAR_SEARCH_M = 250.0


def _sample_depth(
    ds: rasterio.io.DatasetReader, geom, layer: str
) -> tuple[float, float | None]:
    """Return (depth_m, sample_offset_m). Offset is set for point layers only."""
    if layer == LAYER_ROADS:
        return line_max_depth(ds, geom), None
    depth, offset = point_nearby_max_depth(
        ds, geom, search_m=POINT_NEAR_SEARCH_M, wet_m=0.005
    )
    return depth, offset


def _first_exceedance_lead(
    geom,
    layer: str,
    band: str,
    lead_datasets: list[tuple[float, rasterio.io.DatasetReader]],
    storm_total_depth: float,
) -> tuple[float | None, str]:
    """Return (lead_h, note) when cumulative depth first meets the asset's band min.

    If cum lead frames never reach the band but storm-total does, note that
    exceedance is only visible on storm-total (frames are sparse / lower).
    """
    thr = _band_min(band)
    for lead_h, ds in lead_datasets:
        d, _off = _sample_depth(ds, geom, layer)
        if np.isfinite(d) and d >= thr:
            return float(lead_h), f"band first met by +{int(lead_h)}h cum. depth frame"
    if np.isfinite(storm_total_depth) and storm_total_depth >= thr:
        last = lead_datasets[-1][0] if lead_datasets else None
        note = (
            f"not met in cum. frames through +{int(last)}h — present on storm-total only"
            if last is not None
            else "present on storm-total only (no lead frames)"
        )
        return None, note
    return None, "no exceedance"


def build_ranked_assets(
    *,
    gpkg: Path,
    depth_tif: Path,
    lead_tifs: list[tuple[float, Path]] | None = None,
    top_n: int | None = None,
    map_full_geom_roads: int = 60,
    engine_id: str = "pysheds_hand_bathtub_v2",
    engine_role: str = "primary_research_depth",
    engine_label: str = "pysheds HAND/bathtub (citywide · MRMS QPE)",
    access_fixture: Path | dict[str, Any] | None = None,
    access_buffer_m: float = 100.0,
) -> dict[str, Any]:
    """Build ranked wet-asset table + GeoJSON FeatureCollections."""

    lead_tifs = lead_tifs or []
    lead_handles: list[tuple[float, rasterio.io.DatasetReader]] = []
    try:
        for lead_h, path in lead_tifs:
            if path.exists():
                lead_handles.append((float(lead_h), rasterio.open(path)))

        assets: list[dict[str, Any]] = []
        geo_by_layer: dict[str, list[dict[str, Any]]] = {
            LAYER_ROADS: [],
            LAYER_STATIONS: [],
            LAYER_FACILITIES: [],
        }

        with rasterio.open(depth_tif) as ds:
            for layer in (LAYER_ROADS, LAYER_STATIONS, LAYER_FACILITIES):
                gdf = gpd.read_file(gpkg, layer=layer)
                for idx, row in gdf.iterrows():
                    geom = row.geometry
                    depth, sample_offset_m = _sample_depth(ds, geom, layer)
                    band = _band_id(float(depth)) if np.isfinite(depth) else None
                    if not band:
                        continue
                    lonlat = _centroid_lonlat(geom)
                    if lonlat is None:
                        continue
                    lon, lat = lonlat
                    aid = _asset_id(row, layer, int(idx) if isinstance(idx, (int, np.integer)) else len(assets))
                    name = _asset_name(row, layer, int(idx) if isinstance(idx, (int, np.integer)) else 0)
                    lead_h, lead_note = _first_exceedance_lead(
                        geom, layer, band, lead_handles, float(depth)
                    )
                    depth_series_cm: list[float] = []
                    depth_series_leads_h: list[float] = []
                    for lead_i, lead_ds in lead_handles:
                        d_i, _off_i = _sample_depth(lead_ds, geom, layer)
                        depth_series_leads_h.append(float(lead_i))
                        depth_series_cm.append(
                            round(float(d_i) * 100.0, 2) if np.isfinite(d_i) else 0.0
                        )
                    asset_type = {
                        LAYER_ROADS: "road",
                        LAYER_STATIONS: "station",
                        LAYER_FACILITIES: "facility",
                    }.get(layer, layer)
                    props = {
                        "id": aid,
                        "name": name,
                        "asset_type": asset_type,
                        "layer": layer,
                        "max_depth_m": round(float(depth), 4),
                        "max_depth_cm": round(float(depth) * 100.0, 1),
                        "band": band,
                        "band_label": BAND_LABEL_SHORT.get(band, band),
                        "band_full_label": next((b["label"] for b in DEPTH_BANDS if b["id"] == band), band),
                        "first_exceedance_lead_h": lead_h,
                        "first_exceedance_note": lead_note,
                        "depth_series_cm": depth_series_cm,
                        "depth_series_leads_h": depth_series_leads_h,
                        "action_hint": BAND_ACTION_HINTS.get(band, ""),
                        "lon": lon,
                        "lat": lat,
                        "highway": str(row.get("highway") or "") if layer == LAYER_ROADS else None,
                        "facility_type": str(row.get("facility_type") or "") if layer == LAYER_FACILITIES else None,
                        "sample_offset_m": (
                            None
                            if sample_offset_m is None
                            else round(float(sample_offset_m), 1)
                        ),
                        "sample_method": (
                            "line_max"
                            if layer == LAYER_ROADS
                            else f"point_nearby_max_{int(POINT_NEAR_SEARCH_M)}m"
                        ),
                        "engine": engine_id,
                    }
                    assets.append(props)
                    feat_geom = geom.__geo_interface__
                    geo_by_layer[layer].append(
                        {"type": "Feature", "properties": props, "geometry": feat_geom}
                    )

        # Depth sort first; demo geography + access join re-rank below.
        assets.sort(key=lambda a: (-a["max_depth_m"], a["name"]))
        for i, a in enumerate(assets, start=1):
            a["rank"] = i

        counts = {
            "wet_total": len(assets),
            "roads": sum(1 for a in assets if a["layer"] == LAYER_ROADS),
            "stations": sum(1 for a in assets if a["layer"] == LAYER_STATIONS),
            "facilities": sum(1 for a in assets if a["layer"] == LAYER_FACILITIES),
            "by_band": {
                b["id"]: sum(1 for a in assets if a["band"] == b["id"]) for b in DEPTH_BANDS
            },
        }

        fixture_obj: dict[str, Any] | None
        if isinstance(access_fixture, Path):
            fixture_obj = load_access_fixture(access_fixture) if access_fixture.exists() else None
        elif isinstance(access_fixture, dict):
            fixture_obj = access_fixture
        else:
            fixture_obj = None

        payload: dict[str, Any] = {
            "product": "asset_decision_desk",
            "official_nws": False,
            "decision_grade": False,
            "enterprise": False,
            "hens": False,
            "honesty": (
                "Ranked wet assets from research inundation × OSM/demo exposure. "
                "Stations/facilities use max HAND depth within 250 m of the pin "
                "(cell misalignment), not only the single cell under the point. "
                "NOT official NWS thresholds. NOT decision-grade infrastructure guidance."
            ),
            "point_sample": {
                "method": f"point_nearby_max_{int(POINT_NEAR_SEARCH_M)}m",
                "search_m": POINT_NEAR_SEARCH_M,
                "note": (
                    "Point assets often sit off the HAND wet channel; ranking uses "
                    "nearby max depth within search_m (same idea as FloodNet nearest-wet)."
                ),
            },
            "scenario": {
                "id": "ida_mrms_metro",
                "label": "Ida · MRMS QPE · NYC metro (research)",
                "case_study": "Hurricane Ida remnants 2021-09-01",
                "forcing": "mrms_qpe_ida_spatial",
            },
            "depth_engine": {
                "id": engine_id,
                "role": engine_role,
                "label": engine_label,
                "depth_tif": str(depth_tif),
                "note": (
                    "Primary research depth for metro asset ranking. "
                    "Unified pysheds HAND/bathtub on metro DEM × spatial MRMS QPE Ida."
                ),
            },
            "depth_engines_reconcile": {
                "primary": {
                    "id": "pysheds_hand_bathtub_v2",
                    "extent": "metro",
                    "forcing": "spatial_mrms_qpe_ida",
                    "use_for": "Default Asset Decision Desk ranking (primary depth)",
                },
                "alternate": {
                    "id": "sfincs_docker_queens",
                    "extent": "Queens spike domain",
                    "forcing": "spatial MRMS precip grid (HydroMT setup_precip_forcing_from_grid)",
                    "use_for": "Alternate hydro track only — magnitudes not peer-comparable to primary pysheds",
                    "honesty": (
                        "SFINCS Queens and pysheds metro are NOT equally authoritative. "
                        "Different domain/physics — do not treat as peer depth products until calibrated."
                    ),
                },
                "strata_spike": {
                    "id": "strata_sfincs_spike",
                    "use_for": "Methods coupling demo only — NOT Ida decision narrative",
                },
            },
            "depth_bands_m": DEPTH_BANDS,
            "band_action_hints": BAND_ACTION_HINTS,
            "lead_frames_h": [h for h, _ in lead_tifs if Path(_).exists()],
            "depth_series_note": (
                "Per-asset HAND depth (cm) on cum lead frames for selected-card sparkline. "
                "Research only — not street-truth."
            ),
            "counts": counts,
            "assets": assets,
            "all_wet_summary": {
                "n": len(assets),
                "max_depth_m": assets[0]["max_depth_m"] if assets else None,
                "deepest_name": assets[0]["name"] if assets else None,
            },
        }
        apply_access_and_demotion(payload, fixture_obj, buffer_m=access_buffer_m)
        listed = payload["assets"] if top_n is None else payload["assets"][:top_n]
        payload["assets"] = listed
        payload["listed_n"] = len(listed)

        # Full line geometry for deepest roads; centroids otherwise to keep payload light.
        full_road_ids = {
            a["id"]
            for a in payload["assets"]
            if a["layer"] == LAYER_ROADS and a["rank"] <= map_full_geom_roads
        }
        # Refresh feature properties from re-ranked assets
        by_id = {a["id"]: a for a in payload["assets"]}
        features: list[dict[str, Any]] = []
        for layer, feats in geo_by_layer.items():
            for ft in feats:
                props = ft["properties"]
                aid = props["id"]
                if aid in by_id:
                    props = dict(by_id[aid])
                if layer == LAYER_ROADS and aid not in full_road_ids:
                    features.append(
                        {
                            "type": "Feature",
                            "properties": props,
                            "geometry": {
                                "type": "Point",
                                "coordinates": [props["lon"], props["lat"]],
                            },
                        }
                    )
                else:
                    features.append({"type": "Feature", "properties": props, "geometry": ft["geometry"]})

        payload["geojson"] = {"type": "FeatureCollection", "features": features}
        return payload
    finally:
        for _, ds in lead_handles:
            ds.close()


def write_ranked_assets(payload: dict[str, Any], out_json: Path, out_geojson: Path | None = None) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    geo = payload.pop("geojson", None)
    out_json.write_text(json.dumps(payload, indent=2))
    if out_geojson is not None and geo is not None:
        out_geojson.write_text(json.dumps(geo))
        # Re-attach for callers that still hold the dict
        payload["geojson"] = geo
        payload["geojson_file"] = out_geojson.name
