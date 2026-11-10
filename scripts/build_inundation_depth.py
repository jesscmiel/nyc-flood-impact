#!/usr/bin/env python3
"""Estimated research inundation depth from Earth2 precip + citywide DEM (pysheds HAND).

Method
------
1. pysheds: fill pits/depressions, D8 flow direction / accumulation, HAND.
2. Depression bathtub: sink capacity = filled_DEM − DEM; ponding capped by rainfall excess.
3. Local relative-elevation bathtub: rain_excess − (DEM − focal_min).
4. Combine: depth = max(HAND-screened excess, depression fill, relative bathtub).
5. Earth2 Ida precip (mm) is the only weather forcing; runoff coefficient is exploratory.

Honesty
-------
This is **estimated research inundation**, not an official NWS flood warning, not a
calibrated NYC sewer/overland model, and not emergency guidance. No agency flood-crest
or warning threshold is applied. Earth2 storm totals over NYC for this case are ~cm–dm
scale, so depths are correspondingly shallow.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject
from scipy import ndimage

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

# pysheds 0.5 + NumPy 2.x: np.in1d was removed
if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

from pysheds.grid import Grid  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
OUT_DIR = PROCESSED_DIR / "inundation"
DEM_PATH = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
LAND_MASK = PROCESSED_DIR / "land_mask_citywide.tif"
E2_TOTAL = PROCESSED_DIR / "earth2_precip" / "precip_storm_total.tif"
BOUNDS = EXTENTS["citywide"]["bounds"]
RUNOFF_COEFF = 0.70  # exploratory urban excess — NOT calibrated
MIN_DEPTH_M = 0.005
FOCAL_WIN = 9  # cells (~750 m at 3-arcsec) for local relative elev
DEPTH_CMAP = "Blues"


def _rgba_depth(depth_m: np.ndarray, vmax: float = 1.5) -> np.ndarray:
    finite = np.isfinite(depth_m) & (depth_m >= MIN_DEPTH_M)
    data = np.clip(np.where(np.isfinite(depth_m), depth_m, 0.0) / max(vmax, 1e-6), 0, 1)
    rgba = colormaps[DEPTH_CMAP](data, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(220, 40 + (data * 180).astype(np.uint8)), 0)
    return rgba


def _write_tif(path: Path, data: np.ndarray, transform, crs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": -9999.0,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)


def _write_png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)


def _warp_to_dem(src_path: Path, dem_shape, dem_transform, dem_crs) -> np.ndarray:
    dst = np.full(dem_shape, np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dem_transform,
            dst_crs=dem_crs,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    return dst


def compute_terrain(dem_path: Path) -> dict:
    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    pit = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit)
    inflated = grid.resolve_flats(flooded)
    fdir = grid.flowdir(inflated, routing="d8")
    acc = grid.accumulation(fdir, routing="d8")
    acc_a = np.asarray(acc, dtype=np.float64)
    thr = max(50.0, float(np.percentile(acc_a[np.isfinite(acc_a)], 98)))
    hand = grid.compute_hand(fdir, inflated, acc > thr, routing="d8")
    dem_a = np.asarray(dem, dtype=np.float32)
    filled_a = np.asarray(flooded, dtype=np.float32)
    hand_a = np.asarray(hand, dtype=np.float32)
    dem_a[~np.isfinite(dem_a)] = np.nan
    filled_a[~np.isfinite(filled_a)] = np.nan
    hand_a[~np.isfinite(hand_a)] = np.nan
    sink_cap = np.clip(filled_a - dem_a, 0, None)
    return {
        "dem": dem_a,
        "filled": filled_a,
        "hand": hand_a,
        "sink_capacity_m": sink_cap.astype(np.float32),
        "stream_acc_threshold": thr,
    }


def depth_from_rain(
    rain_mm: np.ndarray,
    hand_m: np.ndarray,
    sink_cap_m: np.ndarray,
    dem_m: np.ndarray,
    runoff: float = RUNOFF_COEFF,
) -> np.ndarray:
    rain_m = np.clip(np.nan_to_num(rain_mm, nan=0.0), 0, None) / 1000.0 * runoff

    # HAND-screened excess (near drainage only when HAND < rain)
    hand_depth = rain_m - np.nan_to_num(hand_m, nan=np.inf)
    hand_depth = np.where(np.isfinite(hand_m), hand_depth, np.nan)

    # Depression bathtub: fill sinks up to available excess
    dep_depth = np.minimum(np.nan_to_num(sink_cap_m, nan=0.0), rain_m)

    # Local relative-elevation bathtub
    dem_fill = np.where(np.isfinite(dem_m), dem_m, np.nanmax(dem_m[np.isfinite(dem_m)]))
    focal_min = ndimage.minimum_filter(dem_fill, size=FOCAL_WIN)
    rel = dem_fill - focal_min
    rel_depth = rain_m - rel

    depth = np.fmax(np.fmax(hand_depth, dep_depth), rel_depth)
    depth = np.where(np.isfinite(dem_m), depth, np.nan)
    depth = np.where(depth >= MIN_DEPTH_M, depth, np.nan)
    return depth.astype(np.float32)


def apply_land_mask(depth: np.ndarray, transform, crs) -> np.ndarray:
    if not LAND_MASK.exists():
        return depth
    mask = np.zeros(depth.shape, dtype=np.float32)
    with rasterio.open(LAND_MASK) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=mask,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.nearest,
            src_nodata=src.nodata,
            dst_nodata=0,
        )
    return np.where(mask > 0.5, depth, np.nan)


def main() -> dict:
    if not DEM_PATH.exists():
        raise FileNotFoundError(f"Citywide DEM missing: {DEM_PATH}")
    if not E2_TOTAL.exists():
        raise FileNotFoundError(f"Earth2 storm total missing: {E2_TOTAL}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    print("Computing pysheds HAND + depression terrain on citywide DEM…")
    terrain = compute_terrain(DEM_PATH)
    with rasterio.open(DEM_PATH) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        dem_shape = (dem_ds.height, dem_ds.width)

    hand = terrain["hand"]
    hand_path = OUT_DIR / "hand_citywide.tif"
    _write_tif(hand_path, hand, transform, crs)
    _write_tif(OUT_DIR / "sink_capacity_m.tif", terrain["sink_capacity_m"], transform, crs)

    rain = _warp_to_dem(E2_TOTAL, dem_shape, transform, crs)
    depth = depth_from_rain(rain, hand, terrain["sink_capacity_m"], terrain["dem"])
    depth = apply_land_mask(depth, transform, crs)
    vmax = float(np.nanpercentile(depth[np.isfinite(depth)], 99)) if np.isfinite(depth).any() else 0.1
    vmax = max(0.05, min(vmax, 3.0))

    total_tif = OUT_DIR / "depth_storm_total_m.tif"
    total_png = ASSETS / "depth_storm_total_m.png"
    _write_tif(total_tif, depth, transform, crs)
    _write_png(total_png, _rgba_depth(depth, vmax=vmax))

    lead_frames = []
    for lead in (6, 12, 18, 24):
        src = PROCESSED_DIR / "earth2_precip" / f"precip_lead_{lead:02d}h.tif"
        if not src.exists():
            continue
        rain_l = _warp_to_dem(src, dem_shape, transform, crs)
        d = depth_from_rain(rain_l, hand, terrain["sink_capacity_m"], terrain["dem"])
        d = apply_land_mask(d, transform, crs)
        stem = f"depth_lead_{lead:02d}h_m"
        _write_tif(OUT_DIR / f"{stem}.tif", d, transform, crs)
        _write_png(ASSETS / f"{stem}.png", _rgba_depth(d, vmax=vmax))
        lead_frames.append(
            {
                "lead_hours": lead,
                "png": f"{stem}.png",
                "tif": str(OUT_DIR / f"{stem}.tif"),
                "max_m": float(np.nanmax(d)) if np.isfinite(d).any() else None,
                "wet_fraction": float(np.mean(np.isfinite(d))) if d.size else 0.0,
                "note": "Interval precip → exploratory depth (not cumulative routing).",
            }
        )

    native_paths = [PROCESSED_DIR / "earth2_precip" / f"precip_lead_{h:02d}h.tif" for h in (6, 12, 18, 24)]
    native_paths = [p for p in native_paths if p.exists()]
    cum_frames = []
    if native_paths:
        cum = np.zeros(dem_shape, dtype=np.float32)
        for p in native_paths:
            cum = cum + np.nan_to_num(_warp_to_dem(p, dem_shape, transform, crs), nan=0.0)
            lead = int(p.stem.split("_")[2].replace("h", ""))
            d = depth_from_rain(cum, hand, terrain["sink_capacity_m"], terrain["dem"])
            d = apply_land_mask(d, transform, crs)
            stem = f"depth_cum_lead_{lead:02d}h_m"
            _write_tif(OUT_DIR / f"{stem}.tif", d, transform, crs)
            _write_png(ASSETS / f"{stem}.png", _rgba_depth(d, vmax=vmax))
            cum_frames.append(
                {
                    "lead_hours": lead,
                    "png": f"{stem}.png",
                    "tif": str(OUT_DIR / f"{stem}.tif"),
                    "max_m": float(np.nanmax(d)) if np.isfinite(d).any() else None,
                    "wet_fraction": float(np.mean(np.isfinite(d))) if d.size else 0.0,
                    "cumulative": True,
                }
            )

    leaflet_bounds = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    meta = {
        "product": "estimated_research_inundation_depth",
        "model": "pysheds HAND + depression/relative-elevation rainfall-excess bathtub",
        "engine": "pysheds",
        "dem": str(DEM_PATH),
        "forcing": str(E2_TOTAL),
        "runoff_coefficient": RUNOFF_COEFF,
        "focal_window_cells": FOCAL_WIN,
        "formula": (
            "depth_m = max(HAND excess, min(sink_capacity, rain_m), rain_m − (DEM − focal_min)); "
            "rain_m = runoff_coeff * precip_mm/1000"
        ),
        "units": "meters",
        "disclaimer": (
            "Estimated research inundation only. NOT an official NWS flood warning, "
            "NOT a calibrated NYC DEP/SWMM product, NOT emergency guidance."
        ),
        "not_flood_warning": True,
        "hand_tif": str(hand_path),
        "stream_acc_threshold": terrain["stream_acc_threshold"],
        "storm_total": {
            "png": total_png.name,
            "tif": str(total_tif),
            "max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
            "p95_m": float(np.nanpercentile(depth[np.isfinite(depth)], 95)) if np.isfinite(depth).any() else None,
            "wet_fraction": float(np.mean(np.isfinite(depth))),
            "display_vmax_m": vmax,
            "forcing_max_mm": float(np.nanmax(rain)) if np.isfinite(rain).any() else None,
        },
        "interval_frames": lead_frames,
        "cumulative_frames": cum_frames,
        "bounds": leaflet_bounds,
        "colorbar": {"cmap": DEPTH_CMAP, "units": "m", "label": "Est. depth (m) — research only"},
        "opacity_default": 0.75,
    }
    (OUT_DIR / "inundation_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "inundation_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"max_m": meta["storm_total"]["max_m"], "wet_fraction": meta["storm_total"]["wet_fraction"], "n_cum": len(cum_frames)}, indent=2))
    return meta


if __name__ == "__main__":
    main()
