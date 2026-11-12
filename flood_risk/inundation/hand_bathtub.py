"""Unified pysheds HAND + depression/relative-elevation bathtub parameters.

Single code path for metro / citywide / borough spikes so depths are comparable.
Research estimate only — NOT official NWS / NOT decision-grade.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from scipy import ndimage

if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

from pysheds.grid import Grid  # noqa: E402

# Canonical physics knobs (was inconsistent across borough vs citywide scripts).
RUNOFF_COEFF = 0.70
MIN_DEPTH_M = 0.005
FOCAL_WIN = 9
STREAM_ACC_PERCENTILE = 98.0
STREAM_ACC_MIN = 50.0
HAND_SCALE = 1.0  # depth = rain_m − HAND_SCALE * HAND (full HAND, not 0.15×)
ENGINE_ID = "pysheds_hand_bathtub_v2"
ENGINE_LABEL = "pysheds HAND/bathtub (unified metro path)"


def compute_terrain_from_dem_path(dem_path: Path) -> dict[str, Any]:
    """Fill pits, D8 flow, HAND on accumulation > p98 streams."""
    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    pit = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit)
    inflated = grid.resolve_flats(flooded)
    fdir = grid.flowdir(inflated, routing="d8")
    acc = grid.accumulation(fdir, routing="d8")
    acc_a = np.asarray(acc, dtype=np.float64)
    finite = np.isfinite(acc_a)
    thr = STREAM_ACC_MIN
    if finite.any():
        thr = max(STREAM_ACC_MIN, float(np.percentile(acc_a[finite], STREAM_ACC_PERCENTILE)))
    hand = grid.compute_hand(fdir, inflated, acc > thr, routing="d8")
    dem_a = np.asarray(dem, dtype=np.float32)
    filled_a = np.asarray(flooded, dtype=np.float32)
    hand_a = np.asarray(hand, dtype=np.float32)
    dem_a[~np.isfinite(dem_a)] = np.nan
    filled_a[~np.isfinite(filled_a)] = np.nan
    hand_a[~np.isfinite(hand_a)] = np.nan
    sink_cap = np.clip(filled_a - dem_a, 0, None).astype(np.float32)
    return {
        "dem": dem_a,
        "filled": filled_a,
        "hand": hand_a,
        "sink_capacity_m": sink_cap,
        "stream_acc_threshold": thr,
        "runoff_coeff": RUNOFF_COEFF,
        "focal_window_cells": FOCAL_WIN,
        "hand_scale": HAND_SCALE,
        "engine": ENGINE_ID,
    }


def compute_terrain_from_array(
    dem: np.ndarray,
    transform,
    crs: str = "EPSG:4326",
) -> dict[str, Any]:
    """Same terrain stack from an in-memory DEM (writes a temp GeoTIFF for pysheds)."""
    with tempfile.TemporaryDirectory() as td:
        dem_path = Path(td) / "dem.tif"
        with rasterio.open(
            dem_path,
            "w",
            driver="GTiff",
            height=dem.shape[0],
            width=dem.shape[1],
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.write(np.where(np.isfinite(dem), dem, -9999.0).astype(np.float32), 1)
        return compute_terrain_from_dem_path(dem_path)


def depth_from_rain(
    rain_mm: np.ndarray,
    hand_m: np.ndarray,
    sink_cap_m: np.ndarray,
    dem_m: np.ndarray,
    *,
    runoff: float = RUNOFF_COEFF,
    focal_win: int = FOCAL_WIN,
    hand_scale: float = HAND_SCALE,
    min_depth_m: float = MIN_DEPTH_M,
) -> np.ndarray:
    """Rainfall-excess depth: max(HAND excess, depression bathtub, relative-elev bathtub).

    ``rain_mm`` should already be *effective* precip when the open drainage capacity
    proxy is enabled (see ``drainage_capacity.effective_sink_mm``). Terrain
    ``sink_cap_m`` is depression storage, not sewer capacity.
    """
    rain_m = np.clip(np.nan_to_num(rain_mm, nan=0.0), 0, None) / 1000.0 * runoff
    hand_depth = rain_m - hand_scale * np.nan_to_num(hand_m, nan=np.inf)
    hand_depth = np.where(np.isfinite(hand_m), hand_depth, np.nan)
    dep_depth = np.minimum(np.nan_to_num(sink_cap_m, nan=0.0), rain_m)
    dem_fill = np.where(np.isfinite(dem_m), dem_m, np.nanmax(dem_m[np.isfinite(dem_m)]))
    focal_min = ndimage.minimum_filter(dem_fill, size=focal_win)
    rel = dem_fill - focal_min
    rel_depth = rain_m - rel
    depth = np.fmax(np.fmax(hand_depth, dep_depth), rel_depth)
    depth = np.where(np.isfinite(dem_m), depth, np.nan)
    depth = np.where(depth >= min_depth_m, depth, np.nan)
    return depth.astype(np.float32)


def param_meta() -> dict[str, Any]:
    return {
        "engine": ENGINE_ID,
        "label": ENGINE_LABEL,
        "runoff_coefficient": RUNOFF_COEFF,
        "focal_window_cells": FOCAL_WIN,
        "stream_acc_percentile": STREAM_ACC_PERCENTILE,
        "stream_acc_min": STREAM_ACC_MIN,
        "hand_scale": HAND_SCALE,
        "min_depth_m": MIN_DEPTH_M,
        "formula": (
            "depth_m = max(rain_m − HAND, min(depression_sink, rain_m), rain_m − (DEM − focal_min)); "
            "rain_m = runoff_coeff * effective_precip_mm/1000; "
            "effective_precip from drainage_capacity_proxy_v1 when enabled"
        ),
        "drainage_proxy": "drainage_capacity_proxy_v1",
        "official_nws": False,
        "decision_grade": False,
    }
