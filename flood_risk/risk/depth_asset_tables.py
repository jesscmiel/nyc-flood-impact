"""Depth × asset risk tables (research / not decision-grade).

Counts roads / stations / facilities intersecting estimated inundation depth bands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import rowcol
from shapely.geometry import LineString, Point, shape

# Research heuristic bands — NOT NWS criteria
DEPTH_BANDS = [
    {"id": "ponding", "label": "Ponding ≥3 cm", "min_m": 0.03, "max_m": 0.08},
    {"id": "deep_ponding", "label": "Deep ponding ≥8 cm", "min_m": 0.08, "max_m": 0.15},
    {"id": "hazard", "label": "Hazard ponding ≥15 cm", "min_m": 0.15, "max_m": None},
]


def _sample_depth(ds: rasterio.io.DatasetReader, x: float, y: float) -> float:
    try:
        r, c = rowcol(ds.transform, x, y)
        if r < 0 or c < 0 or r >= ds.height or c >= ds.width:
            return float("nan")
        val = ds.read(1, window=((r, r + 1), (c, c + 1)))[0, 0]
        return float(val)
    except Exception:  # noqa: BLE001
        return float("nan")


def _line_max_depth(ds: rasterio.io.DatasetReader, geom: LineString, step_m_deg: float = 0.0003) -> float:
    if geom.is_empty:
        return float("nan")
    length = geom.length
    n = max(int(length / step_m_deg), 2)
    depths = []
    for i in range(n + 1):
        pt = geom.interpolate(i / n, normalized=True)
        d = _sample_depth(ds, pt.x, pt.y)
        if np.isfinite(d):
            depths.append(d)
    return float(max(depths)) if depths else float("nan")


def _band_id(depth_m: float) -> str | None:
    if not np.isfinite(depth_m) or depth_m < DEPTH_BANDS[0]["min_m"]:
        return None
    for b in reversed(DEPTH_BANDS):
        lo = b["min_m"]
        hi = b["max_m"]
        if depth_m >= lo and (hi is None or depth_m < hi):
            return b["id"]
        if hi is None and depth_m >= lo:
            return b["id"]
    return None


def load_features(path: Path) -> list[dict[str, Any]]:
    geo = json.loads(path.read_text())
    return list(geo.get("features") or [])


def summarize_assets(
    depth_tif: Path,
    roads_path: Path | None,
    stations_path: Path | None,
    facilities_path: Path | None,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    band_counts = {
        "roads": {b["id"]: 0 for b in DEPTH_BANDS},
        "stations": {b["id"]: 0 for b in DEPTH_BANDS},
        "facilities": {b["id"]: 0 for b in DEPTH_BANDS},
    }
    totals = {"roads": 0, "stations": 0, "facilities": 0}
    max_by = {"roads": 0.0, "stations": 0.0, "facilities": 0.0}

    with rasterio.open(depth_tif) as ds:
        if roads_path and roads_path.exists():
            for feat in load_features(roads_path):
                geom = shape(feat["geometry"])
                if geom.geom_type == "MultiLineString":
                    d = max((_line_max_depth(ds, g) for g in geom.geoms), default=float("nan"))
                elif geom.geom_type == "LineString":
                    d = _line_max_depth(ds, geom)
                else:
                    continue
                totals["roads"] += 1
                if np.isfinite(d):
                    max_by["roads"] = max(max_by["roads"], d)
                    bid = _band_id(d)
                    if bid:
                        band_counts["roads"][bid] += 1

        for kind, path in (("stations", stations_path), ("facilities", facilities_path)):
            if not path or not path.exists():
                continue
            for feat in load_features(path):
                geom = shape(feat["geometry"])
                if geom.geom_type == "MultiPoint":
                    pts = list(geom.geoms)
                elif geom.geom_type == "Point":
                    pts = [geom]
                else:
                    # take centroid for polygons
                    pts = [geom.centroid]
                totals[kind] += 1
                depths = [_sample_depth(ds, p.x, p.y) for p in pts]
                depths = [d for d in depths if np.isfinite(d)]
                if not depths:
                    continue
                d = max(depths)
                max_by[kind] = max(max_by[kind], d)
                bid = _band_id(d)
                if bid:
                    band_counts[kind][bid] += 1

    table = []
    for b in DEPTH_BANDS:
        table.append(
            {
                "band": b["id"],
                "label": b["label"],
                "min_m": b["min_m"],
                "max_m": b["max_m"],
                "roads": band_counts["roads"][b["id"]],
                "stations": band_counts["stations"][b["id"]],
                "facilities": band_counts["facilities"][b["id"]],
            }
        )

    wet_assets = {
        "roads": sum(band_counts["roads"].values()),
        "stations": sum(band_counts["stations"].values()),
        "facilities": sum(band_counts["facilities"].values()),
    }

    return {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "honesty": (
            "Depth×asset counts from research inundation (pysheds) × OSM/demo exposure. "
            "NOT official NWS thresholds. NOT decision-grade infrastructure guidance."
        ),
        "scenario": scenario,
        "depth_bands_m": DEPTH_BANDS,
        "totals": totals,
        "wet_assets": wet_assets,
        "max_depth_on_asset_m": max_by,
        "table": table,
    }
