"""Citywide exposure GeoPackage builder + reliable depth intersects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.sample import sample_gen
from shapely.geometry import LineString, MultiLineString, Point, shape


LAYER_ROADS = "roads"
LAYER_STATIONS = "stations"
LAYER_FACILITIES = "facilities"


def _gdf_from_geojson(path: Path, layer_hint: str) -> gpd.GeoDataFrame:
    raw = json.loads(path.read_text())
    feats = raw.get("features") or []
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    gdf["exposure_layer"] = layer_hint
    gdf["source_file"] = path.name
    return gdf


def build_exposure_gpkg(
    *,
    roads_geojson: Path,
    stations_geojson: Path,
    facilities_geojson: Path,
    out_gpkg: Path,
) -> dict[str, Any]:
    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    if out_gpkg.exists():
        out_gpkg.unlink()

    layers = {
        LAYER_ROADS: _gdf_from_geojson(roads_geojson, LAYER_ROADS),
        LAYER_STATIONS: _gdf_from_geojson(stations_geojson, LAYER_STATIONS),
        LAYER_FACILITIES: _gdf_from_geojson(facilities_geojson, LAYER_FACILITIES),
    }
    meta = {"layers": {}, "path": str(out_gpkg), "crs": "EPSG:4326", "official": False}
    for name, gdf in layers.items():
        if gdf.empty:
            raise RuntimeError(f"exposure layer empty: {name}")
        # Drop non-serializable columns for GPKG
        keep = [c for c in gdf.columns if c == "geometry" or gdf[c].dtype != "O" or c in ("name", "highway", "facility_type", "exposure_layer", "source_file", "railway")]
        # Always keep common string props if present
        for c in list(gdf.columns):
            if c != "geometry" and c not in keep:
                if pd.api.types.is_string_dtype(gdf[c]) or gdf[c].dtype == object:
                    gdf[c] = gdf[c].astype(str)
                    keep.append(c)
        gdf = gdf[[c for c in keep if c in gdf.columns]].copy()
        gdf.to_file(out_gpkg, layer=name, driver="GPKG")
        meta["layers"][name] = {"n": int(len(gdf)), "geom_types": sorted(set(gdf.geom_type))}
    meta_path = out_gpkg.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def _sample_points(ds: rasterio.io.DatasetReader, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    coords = list(zip(xs.tolist(), ys.tolist()))
    vals = np.array([v[0] for v in sample_gen(ds, coords)], dtype=np.float64)
    nodata = ds.nodata
    if nodata is not None:
        vals = np.where(vals == nodata, np.nan, vals)
    return vals


def line_max_depth(ds: rasterio.io.DatasetReader, geom, step_deg: float = 0.00035) -> float:
    if geom is None or geom.is_empty:
        return float("nan")
    if isinstance(geom, MultiLineString):
        return float(np.nanmax([line_max_depth(ds, g, step_deg) for g in geom.geoms]))
    if not isinstance(geom, LineString):
        # fallback centroid
        c = geom.centroid
        return float(_sample_points(ds, np.array([c.x]), np.array([c.y]))[0])
    n = max(int(geom.length / step_deg), 2)
    xs, ys = [], []
    for i in range(n + 1):
        p = geom.interpolate(i / n, normalized=True)
        xs.append(p.x)
        ys.append(p.y)
    vals = _sample_points(ds, np.asarray(xs), np.asarray(ys))
    return float(np.nanmax(vals)) if np.isfinite(vals).any() else float("nan")


def point_depth(ds: rasterio.io.DatasetReader, geom) -> float:
    if geom is None or geom.is_empty:
        return float("nan")
    if geom.geom_type == "MultiPoint":
        vals = [_sample_points(ds, np.array([p.x]), np.array([p.y]))[0] for p in geom.geoms]
        return float(np.nanmax(vals)) if vals else float("nan")
    if geom.geom_type != "Point":
        c = geom.centroid
        return float(_sample_points(ds, np.array([c.x]), np.array([c.y]))[0])
    return float(_sample_points(ds, np.array([geom.x]), np.array([geom.y]))[0])


def point_nearby_max_depth(
    ds: rasterio.io.DatasetReader,
    geom,
    *,
    search_m: float = 250.0,
    wet_m: float = 0.005,
) -> tuple[float, float | None]:
    """Max depth within ~search_m of a point (HAND cell misalignment).

    Returns (depth_m, offset_m). Offset is None when the sample is the pin cell
    or when no wet cell is found. Same rationale as FloodNet nearest-wet checks.
    """
    from rasterio.transform import rowcol, xy

    if geom is None or geom.is_empty:
        return float("nan"), None
    if geom.geom_type == "MultiPoint":
        best_d, best_off = float("nan"), None
        for p in geom.geoms:
            d, off = point_nearby_max_depth(ds, p, search_m=search_m, wet_m=wet_m)
            if np.isfinite(d) and (not np.isfinite(best_d) or d > best_d):
                best_d, best_off = d, off
        return best_d, best_off
    if geom.geom_type != "Point":
        geom = geom.centroid

    lon, lat = float(geom.x), float(geom.y)
    direct = point_depth(ds, geom)
    row, col = rowcol(ds.transform, lon, lat)
    if not (0 <= row < ds.height and 0 <= col < ds.width):
        return direct, None

    m_per_deg_lat = 110540.0
    m_per_deg_lon = 111320.0 * float(np.cos(np.deg2rad(lat)))
    px_m = abs(ds.res[0]) * m_per_deg_lon
    py_m = abs(ds.res[1]) * m_per_deg_lat
    rad_x = max(1, int(np.ceil(search_m / max(px_m, 1e-6))))
    rad_y = max(1, int(np.ceil(search_m / max(py_m, 1e-6))))
    r0, r1 = max(0, row - rad_y), min(ds.height, row + rad_y + 1)
    c0, c1 = max(0, col - rad_x), min(ds.width, col + rad_x + 1)
    win = ds.read(1, window=((r0, r1), (c0, c1))).astype(np.float64)
    if ds.nodata is not None:
        win = np.where(win == ds.nodata, np.nan, win)
    win = np.where(win < -100, np.nan, win)

    best: tuple[float, float] | None = None  # depth, dist_m
    for i in range(win.shape[0]):
        for j in range(win.shape[1]):
            d = win[i, j]
            if not np.isfinite(d) or d < wet_m:
                continue
            rr, cc = r0 + i, c0 + j
            x, y = xy(ds.transform, rr, cc, offset="center")
            dist = float(
                np.hypot((float(x) - lon) * m_per_deg_lon, (float(y) - lat) * m_per_deg_lat)
            )
            if dist > search_m:
                continue
            if best is None or d > best[0] or (d == best[0] and dist < best[1]):
                best = (float(d), dist)

    if best is None:
        return direct, None
    depth, dist = best
    # Prefer nearby max when it exceeds the pin cell (typical channel offset).
    if np.isfinite(direct) and direct >= depth:
        return float(direct), 0.0 if dist < 1.0 else None
    return float(depth), float(dist)


def intersect_depth_gpkg(
    gpkg: Path,
    depth_tif: Path,
    bands: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return per-layer depth stats and band counts using GeoPackage layers."""

    def band_id(depth_m: float) -> str | None:
        if not np.isfinite(depth_m) or depth_m < bands[0]["min_m"]:
            return None
        for b in reversed(bands):
            lo, hi = b["min_m"], b["max_m"]
            if depth_m >= lo and (hi is None or depth_m < hi):
                return b["id"]
            if hi is None and depth_m >= lo:
                return b["id"]
        return None

    out: dict[str, Any] = {"gpkg": str(gpkg), "depth_tif": str(depth_tif), "layers": {}}
    with rasterio.open(depth_tif) as ds:
        for layer in (LAYER_ROADS, LAYER_STATIONS, LAYER_FACILITIES):
            gdf = gpd.read_file(gpkg, layer=layer)
            depths = []
            for geom in gdf.geometry:
                if layer == LAYER_ROADS:
                    depths.append(line_max_depth(ds, geom))
                else:
                    depths.append(point_depth(ds, geom))
            arr = np.asarray(depths, dtype=np.float64)
            band_counts = {b["id"]: 0 for b in bands}
            for d in arr:
                bid = band_id(float(d))
                if bid:
                    band_counts[bid] += 1
            wet = int(sum(band_counts.values()))
            out["layers"][layer] = {
                "n": int(len(gdf)),
                "wet": wet,
                "max_depth_m": float(np.nanmax(arr)) if np.isfinite(arr).any() else None,
                "mean_wet_m": float(np.nanmean(arr[arr >= bands[0]["min_m"]])) if np.any(arr >= bands[0]["min_m"]) else 0.0,
                "band_counts": band_counts,
            }
    return out
