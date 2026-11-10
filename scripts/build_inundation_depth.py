#!/usr/bin/env python3
"""Estimated research inundation depth from precip forcing + citywide DEM (pysheds HAND).

Builds per-forcing depth sets:
- earth2_control — Earth2 Ida storm total / cumulative leads (primary storm path)
- mrms_qpe_ida — NOAA MRMS Multi-Sensor QPE (~1 km) Ida alt scenario

Method
------
1. pysheds: fill pits/depressions, D8 flow, HAND.
2. Depression bathtub + local relative-elevation bathtub + HAND excess.
3. Land-mask water.

Honesty
-------
Estimated research inundation only — NOT an official NWS flood warning, NOT calibrated
NYC DEP/SWMM, NOT emergency guidance.
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

if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

from pysheds.grid import Grid  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
OUT_DIR = PROCESSED_DIR / "inundation"
DEM_PATH = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
LAND_MASK = PROCESSED_DIR / "land_mask_citywide.tif"
BOUNDS = EXTENTS["citywide"]["bounds"]
RUNOFF_COEFF = 0.70
MIN_DEPTH_M = 0.005
FOCAL_WIN = 9
DEPTH_CMAP = "Blues"

FORCINGS = {
    "earth2_control": {
        "label": "Earth2 (primary) forcing",
        "storm_path_id": "earth2_control",
        "total": PROCESSED_DIR / "earth2_precip" / "precip_storm_total.tif",
        "leads": [
            (6, PROCESSED_DIR / "earth2_precip" / "precip_lead_06h.tif"),
            (12, PROCESSED_DIR / "earth2_precip" / "precip_lead_12h.tif"),
            (18, PROCESSED_DIR / "earth2_precip" / "precip_lead_18h.tif"),
            (24, PROCESSED_DIR / "earth2_precip" / "precip_lead_24h.tif"),
        ],
        "prefix": "depth_",
        "source_note": "Earth2 FCN+PrecipitationAFNO Ida precip",
    },
    "mrms_qpe_ida": {
        "label": "MRMS QPE Ida (~1 km) alt forcing",
        "storm_path_id": "mrms_qpe_ida",
        "total": PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif",
        "leads": [
            (6, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_06h.tif"),
            (12, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_12h.tif"),
            (18, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_18h.tif"),
            (24, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_24h.tif"),
        ],
        # Fallback to raw MRMS dir if export not present
        "total_fallback": PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif",
        "leads_fallback": [
            (6, PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_lead_06h_citywide.tif"),
            (12, PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_lead_12h_citywide.tif"),
            (18, PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_lead_18h_citywide.tif"),
            (24, PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_lead_24h_citywide.tif"),
        ],
        "prefix": "depth_mrms_",
        "source_note": (
            "NOAA MRMS Multi-Sensor QPE (~1 km) — labeled alternate Ida scenario forcing. "
            "NOT a live competing weather product."
        ),
    },
}


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
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        reproject(
            source=data,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dem_transform,
            dst_crs=dem_crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
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
    hand_depth = rain_m - np.nan_to_num(hand_m, nan=np.inf)
    hand_depth = np.where(np.isfinite(hand_m), hand_depth, np.nan)
    dep_depth = np.minimum(np.nan_to_num(sink_cap_m, nan=0.0), rain_m)
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


def _resolve_forcing(cfg: dict) -> tuple[Path | None, list[tuple[int, Path]]]:
    total = cfg["total"] if cfg["total"].exists() else cfg.get("total_fallback")
    if total is not None and not Path(total).exists():
        total = None
    leads = []
    for lead, path in cfg["leads"]:
        p = path if path.exists() else None
        if p is None:
            for fl, fp in cfg.get("leads_fallback") or []:
                if fl == lead and fp.exists():
                    p = fp
                    break
        if p is not None:
            leads.append((lead, p))
    return (Path(total) if total else None), leads


def export_forcing_set(
    key: str,
    cfg: dict,
    terrain: dict,
    dem_shape,
    transform,
    crs,
) -> dict | None:
    total_path, lead_paths = _resolve_forcing(cfg)
    if total_path is None and not lead_paths:
        print(f"  skip {key}: no precip forcing files")
        return None

    hand = terrain["hand"]
    sink = terrain["sink_capacity_m"]
    dem = terrain["dem"]
    prefix = cfg["prefix"]

    # Prefer storm total; else sum leads
    if total_path is not None:
        rain = _warp_to_dem(total_path, dem_shape, transform, crs)
        forcing_used = str(total_path)
    else:
        rain = np.zeros(dem_shape, dtype=np.float32)
        for _, p in lead_paths:
            rain = rain + np.nan_to_num(_warp_to_dem(p, dem_shape, transform, crs), nan=0.0)
        forcing_used = "sum(" + ",".join(str(p) for _, p in lead_paths) + ")"

    depth = depth_from_rain(rain, hand, sink, dem)
    depth = apply_land_mask(depth, transform, crs)
    vmax = float(np.nanpercentile(depth[np.isfinite(depth)], 99)) if np.isfinite(depth).any() else 0.1
    vmax = max(0.05, min(vmax, 3.0))

    total_tif = OUT_DIR / f"{prefix}storm_total_m.tif"
    total_png = f"{prefix}storm_total_m.png"
    _write_tif(total_tif, depth, transform, crs)
    _write_png(ASSETS / total_png, _rgba_depth(depth, vmax=vmax))

    interval_frames = []
    for lead, path in lead_paths:
        rain_l = _warp_to_dem(path, dem_shape, transform, crs)
        d = depth_from_rain(rain_l, hand, sink, dem)
        d = apply_land_mask(d, transform, crs)
        stem = f"{prefix}lead_{lead:02d}h_m"
        _write_tif(OUT_DIR / f"{stem}.tif", d, transform, crs)
        _write_png(ASSETS / f"{stem}.png", _rgba_depth(d, vmax=vmax))
        interval_frames.append(
            {
                "lead_hours": lead,
                "png": f"{stem}.png",
                "tif": str(OUT_DIR / f"{stem}.tif"),
                "max_m": float(np.nanmax(d)) if np.isfinite(d).any() else None,
                "wet_fraction": float(np.mean(np.isfinite(d))) if d.size else 0.0,
            }
        )

    cum_frames = []
    if lead_paths:
        cum = np.zeros(dem_shape, dtype=np.float32)
        for lead, path in lead_paths:
            cum = cum + np.nan_to_num(_warp_to_dem(path, dem_shape, transform, crs), nan=0.0)
            d = depth_from_rain(cum, hand, sink, dem)
            d = apply_land_mask(d, transform, crs)
            stem = f"{prefix}cum_lead_{lead:02d}h_m"
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
    return {
        "id": key,
        "storm_path_id": cfg["storm_path_id"],
        "label": cfg["label"],
        "source_note": cfg["source_note"],
        "forcing": forcing_used,
        "storm_total": {
            "png": total_png,
            "tif": str(total_tif),
            "max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
            "p95_m": float(np.nanpercentile(depth[np.isfinite(depth)], 95)) if np.isfinite(depth).any() else None,
            "wet_fraction": float(np.mean(np.isfinite(depth))),
            "display_vmax_m": vmax,
            "forcing_max_mm": float(np.nanmax(rain)) if np.isfinite(rain).any() else None,
        },
        "interval_frames": interval_frames,
        "cumulative_frames": cum_frames,
        "bounds": leaflet_bounds,
        "colorbar": {"cmap": DEPTH_CMAP, "units": "m", "label": "Est. depth (m) — NOT flood warning"},
        "opacity_default": 0.75,
        "not_flood_warning": True,
    }


def main() -> dict:
    if not DEM_PATH.exists():
        raise FileNotFoundError(f"Citywide DEM missing: {DEM_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    print("Computing pysheds HAND + depression terrain on citywide DEM…")
    terrain = compute_terrain(DEM_PATH)
    with rasterio.open(DEM_PATH) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        dem_shape = (dem_ds.height, dem_ds.width)

    _write_tif(OUT_DIR / "hand_citywide.tif", terrain["hand"], transform, crs)
    _write_tif(OUT_DIR / "sink_capacity_m.tif", terrain["sink_capacity_m"], transform, crs)

    by_path: dict[str, dict] = {}
    for key, cfg in FORCINGS.items():
        print(f"Exporting depth set for {key}…")
        result = export_forcing_set(key, cfg, terrain, dem_shape, transform, crs)
        if result:
            by_path[key] = result
            print(
                json.dumps(
                    {
                        "id": key,
                        "max_m": result["storm_total"]["max_m"],
                        "wet_fraction": result["storm_total"]["wet_fraction"],
                        "forcing_max_mm": result["storm_total"]["forcing_max_mm"],
                    }
                )
            )

    if not by_path:
        raise RuntimeError("No inundation depth sets produced")

    # Backward-compatible top-level fields = Earth2 primary set (or first available)
    primary = by_path.get("earth2_control") or next(iter(by_path.values()))
    # Preferred display when user selects hi-res alt: mrms set
    preferred_hires = by_path.get("mrms_qpe_ida")

    leaflet_bounds = primary["bounds"]
    meta = {
        "product": "estimated_research_inundation_depth",
        "model": "pysheds HAND + depression/relative-elevation rainfall-excess bathtub",
        "engine": "pysheds",
        "dem": str(DEM_PATH),
        "runoff_coefficient": RUNOFF_COEFF,
        "focal_window_cells": FOCAL_WIN,
        "formula": (
            "depth_m = max(HAND excess, min(sink_capacity, rain_m), rain_m − (DEM − focal_min)); "
            "rain_m = runoff_coeff * precip_mm/1000"
        ),
        "units": "meters",
        "disclaimer": (
            "Estimated research inundation only. NOT an official NWS flood warning, "
            "NOT a calibrated NYC DEP/SWMM product, NOT emergency guidance. "
            "Depth follows the selected storm path forcing when a matching depth set exists "
            "(Earth2 primary or MRMS QPE Ida alt)."
        ),
        "not_flood_warning": True,
        "hand_tif": str(OUT_DIR / "hand_citywide.tif"),
        "stream_acc_threshold": terrain["stream_acc_threshold"],
        "default_depth_path": primary["id"],
        "by_path": by_path,
        # Flat aliases for Earth2 (backward compatible with prior UI)
        "storm_total": primary["storm_total"],
        "interval_frames": primary["interval_frames"],
        "cumulative_frames": primary["cumulative_frames"],
        "bounds": leaflet_bounds,
        "colorbar": primary["colorbar"],
        "opacity_default": 0.75,
        "hires_alt_depth_path": preferred_hires["id"] if preferred_hires else None,
    }
    (OUT_DIR / "inundation_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "inundation_meta.json").write_text(json.dumps(meta, indent=2))
    print(
        json.dumps(
            {
                "paths": list(by_path.keys()),
                "earth2_max_m": (by_path.get("earth2_control") or {}).get("storm_total", {}).get("max_m"),
                "mrms_max_m": (by_path.get("mrms_qpe_ida") or {}).get("storm_total", {}).get("max_m"),
            },
            indent=2,
        )
    )
    return meta


if __name__ == "__main__":
    main()
