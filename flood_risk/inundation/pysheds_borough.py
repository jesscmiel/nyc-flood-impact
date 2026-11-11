"""pysheds HAND/bathtub inundation for a bbox clip — uses unified hand_bathtub params.

Research estimate only — NOT official NWS flood warning / NOT decision-grade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.mask import mask as rio_mask
from rasterio.warp import reproject
from shapely.geometry import box, mapping

from flood_risk.inundation.hand_bathtub import (
    ENGINE_ID,
    MIN_DEPTH_M,
    RUNOFF_COEFF,
    compute_terrain_from_array,
    depth_from_rain,
    param_meta,
)


def _read_clip(path: Path, bounds: dict[str, float]) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    geom = [mapping(box(bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"]))]
    with rasterio.open(path) as src:
        data, transform = rio_mask(src, geom, crop=True, filled=True, nodata=np.nan)
        arr = data[0].astype(np.float32)
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        return arr, transform, src.crs


def _reproject_to(src_path: Path, shape: tuple[int, int], transform, crs) -> np.ndarray:
    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        reproject(
            source=data,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    return dst


def _write_tif(path: Path, data: np.ndarray, transform, crs="EPSG:4326") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(data.astype(np.float32), 1)


def _write_png(path: Path, depth: np.ndarray, vmax: float | None = None) -> None:
    vmax = float(
        vmax
        or max(
            np.nanpercentile(depth[np.isfinite(depth) & (depth > 0)], 98) if np.any(depth > 0) else 0.1,
            0.05,
        )
    )
    cmap = colormaps["Blues"]
    norm = np.clip(np.nan_to_num(depth, nan=0.0) / vmax, 0, 1)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(depth > MIN_DEPTH_M, np.clip(80 + norm * 175, 0, 255).astype(np.uint8), 0)
    Image.fromarray(rgba, "RGBA").save(path)


def run_borough_spike(
    dem_path: Path,
    rain_path: Path,
    bounds: dict[str, float],
    out_dir: Path,
    assets_dir: Path,
    borough_id: str = "south_queens",
    forcing_id: str = "mrms_qpe_ida",
) -> dict[str, Any]:
    dem, transform, crs = _read_clip(dem_path, bounds)
    rain_mm = _reproject_to(rain_path, dem.shape, transform, crs)
    terrain = compute_terrain_from_array(dem, transform, crs=str(crs) if crs else "EPSG:4326")
    depth = depth_from_rain(
        rain_mm,
        terrain["hand"],
        terrain["sink_capacity_m"],
        terrain["dem"],
    )
    # PNG writer expects zeros rather than NaN for dry cells
    depth_png = np.where(np.isfinite(depth), depth, 0.0).astype(np.float32)

    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    tif = out_dir / f"depth_{borough_id}_{forcing_id}_storm_total_m.tif"
    png = assets_dir / f"depth_{borough_id}_{forcing_id}_storm_total_m.png"
    _write_tif(tif, depth_png, transform, crs)
    _write_tif(out_dir / f"hand_{borough_id}.tif", terrain["hand"], transform, crs)
    _write_png(png, depth_png)

    meta = {
        "borough_id": borough_id,
        "forcing_id": forcing_id,
        "engine": ENGINE_ID,
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "runoff_coeff": RUNOFF_COEFF,
        "params": param_meta(),
        "bounds": bounds,
        "shape": list(depth.shape),
        "max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
        "mean_wet_m": float(np.nanmean(depth[np.isfinite(depth)])) if np.isfinite(depth).any() else 0.0,
        "wet_fraction": float(np.mean(np.isfinite(depth) & (depth >= MIN_DEPTH_M))),
        "tif": str(tif),
        "png": png.name,
        "honesty": (
            "Research borough spike (unified pysheds HAND/bathtub). NOT official NWS. "
            "SFINCS remains alternate hydro track until spatially forced + comparable."
        ),
    }
    (out_dir / f"depth_{borough_id}_{forcing_id}_meta.json").write_text(json.dumps(meta, indent=2))
    (assets_dir / f"depth_{borough_id}_{forcing_id}_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
