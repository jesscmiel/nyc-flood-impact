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

from flood_risk.inundation.hand_bathtub import (
    ENGINE_ID,
    FOCAL_WIN,
    MIN_DEPTH_M,
    RUNOFF_COEFF,
    compute_terrain_from_dem_path,
    depth_from_rain as unified_depth_from_rain,
    param_meta,
)
from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT

ASSETS = FIGURES_DIR / "product_assets"
OUT_DIR = PROCESSED_DIR / "inundation"
# Prefer metro hi-res DEM after rebuild; fall back to legacy citywide.
_METRO_DEM = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
_CITY_DEM = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
DEM_PATH = _METRO_DEM if _METRO_DEM.exists() else _CITY_DEM
LAND_MASK = (
    PROCESSED_DIR / "land_mask_metro.tif"
    if (PROCESSED_DIR / "land_mask_metro.tif").exists()
    else PROCESSED_DIR / "land_mask_citywide.tif"
)
_EXTENT_ID = PRIMARY_DATA_EXTENT if DEM_PATH == _METRO_DEM else "citywide"
BOUNDS = EXTENTS[_EXTENT_ID]["bounds"]
DEPTH_CMAP = "Blues"

FORCINGS = {
    "mrms_qpe_ida": {
        "label": "MRMS QPE Ida (~1 km) primary forcing",
        "storm_path_id": "mrms_qpe_ida",
        "total": PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif",
        "leads": [
            (6, PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_lead_06h.tif"),
            (12, PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_lead_12h.tif"),
            (18, PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_lead_18h.tif"),
            (24, PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_lead_24h.tif"),
        ],
        "total_fallback": PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif",
        "leads_fallback": [
            (6, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_06h.tif"),
            (12, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_12h.tif"),
            (18, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_18h.tif"),
            (24, PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_lead_24h.tif"),
        ],
        "prefix": "depth_mrms_",
        "source_note": (
            "NOAA MRMS Multi-Sensor QPE (~1 km) — primary Ida forcing (spatial, never domain-mean)."
        ),
    },
    "earth2_control": {
        "label": "Earth2 (scenario) forcing",
        "storm_path_id": "earth2_control",
        "total": PROCESSED_DIR / "earth2_precip" / "precip_storm_total.tif",
        "leads": [
            (6, PROCESSED_DIR / "earth2_precip" / "precip_lead_06h.tif"),
            (12, PROCESSED_DIR / "earth2_precip" / "precip_lead_12h.tif"),
            (18, PROCESSED_DIR / "earth2_precip" / "precip_lead_18h.tif"),
            (24, PROCESSED_DIR / "earth2_precip" / "precip_lead_24h.tif"),
        ],
        "prefix": "depth_",
        "source_note": "Earth2 FCN+PrecipitationAFNO Ida precip — labeled AI scenario only",
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
    return compute_terrain_from_dem_path(dem_path)


def depth_from_rain(
    rain_mm: np.ndarray,
    hand_m: np.ndarray,
    sink_cap_m: np.ndarray,
    dem_m: np.ndarray,
    runoff: float = RUNOFF_COEFF,
) -> np.ndarray:
    return unified_depth_from_rain(
        rain_mm, hand_m, sink_cap_m, dem_m, runoff=runoff
    )


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

    print(f"Computing unified HAND/bathtub terrain on {_EXTENT_ID} DEM…")
    terrain = compute_terrain(DEM_PATH)
    with rasterio.open(DEM_PATH) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        dem_shape = (dem_ds.height, dem_ds.width)

    hand_name = "hand_metro.tif" if _EXTENT_ID == "metro" else "hand_citywide.tif"
    _write_tif(OUT_DIR / hand_name, terrain["hand"], transform, crs)
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

    # Primary = MRMS spatial; Earth2 remains labeled scenario
    primary = by_path.get("mrms_qpe_ida") or next(iter(by_path.values()))
    scenario = by_path.get("earth2_control")

    leaflet_bounds = primary["bounds"]
    meta = {
        "product": "estimated_research_inundation_depth",
        "primary": True,
        "role": "primary_depth",
        "extent": _EXTENT_ID,
        "model": "pysheds HAND + depression/relative-elevation rainfall-excess bathtub",
        "engine": ENGINE_ID,
        "dem": str(DEM_PATH),
        "units": "meters",
        "disclaimer": (
            "Primary research depth = unified pysheds on metro/citywide DEM × spatial MRMS. "
            "Earth2 depth set is a labeled AI scenario only. NOT official NWS / NOT decision-grade. "
            "SFINCS is an alternate hydro track until comparable."
        ),
        "not_flood_warning": True,
        "hand_tif": str(OUT_DIR / hand_name),
        "stream_acc_threshold": terrain["stream_acc_threshold"],
        "default_depth_path": primary["id"],
        "by_path": by_path,
        "storm_total": primary["storm_total"],
        "interval_frames": primary["interval_frames"],
        "cumulative_frames": primary["cumulative_frames"],
        "bounds": leaflet_bounds,
        "colorbar": primary["colorbar"],
        "opacity_default": 0.75,
        "scenario_depth_path": scenario["id"] if scenario else None,
        **param_meta(),
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
