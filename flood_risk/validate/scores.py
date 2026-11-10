"""Quantitative validation scores vs 311 / gauges (exploratory, not certified skill)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.sample import sample_gen
from shapely.geometry import shape


def _load_points(geojson: Path) -> list[tuple[float, float, dict]]:
    raw = json.loads(geojson.read_text())
    out = []
    for f in raw.get("features") or []:
        g = shape(f["geometry"])
        if g.is_empty:
            continue
        if g.geom_type == "Point":
            out.append((g.x, g.y, f.get("properties") or {}))
        elif g.geom_type == "MultiPoint":
            for p in g.geoms:
                out.append((p.x, p.y, f.get("properties") or {}))
        else:
            c = g.centroid
            out.append((c.x, c.y, f.get("properties") or {}))
    return out


def _sample(ds: rasterio.io.DatasetReader, pts: list[tuple[float, float, dict]]) -> np.ndarray:
    if not pts:
        return np.array([], dtype=np.float64)
    coords = [(x, y) for x, y, _ in pts]
    vals = np.array([v[0] for v in sample_gen(ds, coords)], dtype=np.float64)
    if ds.nodata is not None:
        vals = np.where(vals == ds.nodata, np.nan, vals)
    return vals


def score_points_on_depth(
    *,
    depth_tif: Path,
    reports_geojson: Path | None,
    gauges_geojson: Path | None,
    depth_hit_m: float = 0.03,
) -> dict[str, Any]:
    """Hit-rate style scores: fraction of obs points landing on estimated wet cells."""
    with rasterio.open(depth_tif) as ds:
        reports = _load_points(reports_geojson) if reports_geojson and reports_geojson.exists() else []
        gauges = _load_points(gauges_geojson) if gauges_geojson and gauges_geojson.exists() else []
        r_depth = _sample(ds, reports)
        g_depth = _sample(ds, gauges)

    def pack(name: str, pts, depths: np.ndarray) -> dict[str, Any]:
        n = len(pts)
        finite = np.isfinite(depths)
        n_valid = int(finite.sum())
        hits = int(((depths >= depth_hit_m) & finite).sum()) if n else 0
        hit_rate = (hits / n_valid) if n_valid else None
        return {
            "name": name,
            "n_points": n,
            "n_sampled": n_valid,
            "n_hits_depth_ge": hits,
            "depth_threshold_m": depth_hit_m,
            "hit_rate": hit_rate,
            "mean_depth_at_points_m": float(np.nanmean(depths)) if n_valid else None,
            "max_depth_at_points_m": float(np.nanmax(depths)) if n_valid else None,
        }

    r = pack("311_reports", reports, r_depth)
    g = pack("ahps_gauges", gauges, g_depth)

    # Confidence heuristic from sample size + agreement
    rates = [x["hit_rate"] for x in (r, g) if x["hit_rate"] is not None]
    n_tot = r["n_sampled"] + g["n_sampled"]
    if n_tot < 20 or not rates:
        conf = "very_low"
        conf_note = "Too few collocated samples for stable skill claims."
    elif min(rates) < 0.2:
        conf = "low"
        conf_note = "Low hit rates vs depth — expect false alarms / misses; research only."
    elif min(rates) < 0.5:
        conf = "low_moderate"
        conf_note = "Partial spatial agreement with obs points; not certified skill."
    else:
        conf = "moderate_research"
        conf_note = "Higher hit rates on this fixture only — still not decision-grade validation."

    return {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "depth_tif": str(depth_tif),
        "scores": {"reports_311": r, "gauges": g},
        "summary": {
            "hit_rate_311": r["hit_rate"],
            "hit_rate_gauges": g["hit_rate"],
            "n_311": r["n_sampled"],
            "n_gauges": g["n_sampled"],
        },
        "confidence": {"level": conf, "note": conf_note},
        "honesty": (
            "Exploratory collocation of 311/AHPS points on research depth. "
            "Not certified verification skill. NOT NWS validation."
        ),
    }
