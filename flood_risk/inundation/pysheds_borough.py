"""Improved pysheds HAND/bathtub inundation for one borough (South Queens spike).

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
from scipy import ndimage
from shapely.geometry import box, mapping

if not hasattr(np, "in1d"):
    np.in1d = np.isin  # type: ignore[attr-defined]

from pysheds.grid import Grid  # noqa: E402

RUNOFF_COEFF = 0.75
MIN_DEPTH_M = 0.005
FOCAL_WIN = 7


def _window_from_bounds(src: rasterio.io.DatasetReader, bounds: dict[str, float]):
    from rasterio.windows import from_bounds

    return from_bounds(bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"], src.transform)


def _read_clip(path: Path, bounds: dict[str, float]) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    geom = [mapping(box(bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"]))]
    with rasterio.open(path) as src:
        data, transform = rio_mask(src, geom, crop=True, filled=True, nodata=np.nan)
        arr = data[0].astype(np.float32)
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        return arr, transform, src.crs


def _reproject_to(src_path: Path, shape: tuple[int, int], transform, crs, bounds_clip: dict[str, float] | None = None) -> np.ndarray:
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


def compute_hand_bathtub(dem: np.ndarray, rain_m: np.ndarray, transform) -> dict[str, np.ndarray]:
    """Return depth_m, hand, sink_capacity using pysheds + local bathtub."""
    # pysheds wants a file path — write a temp grid
    import tempfile

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
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999,
        ) as dst:
            out = np.where(np.isfinite(dem), dem, -9999).astype(np.float32)
            dst.write(out, 1)

        grid = Grid.from_raster(str(dem_path))
        dem_g = grid.read_raster(str(dem_path))
        pit = grid.fill_pits(dem_g)
        flooded = grid.fill_depressions(pit)
        inflated = grid.resolve_flats(flooded)
        fdir = grid.flowdir(inflated)
        hand = np.asarray(grid.compute_hand(fdir, inflated, np.ones_like(inflated, dtype=bool)), dtype=np.float32)

    dem_f = dem.astype(np.float32)
    rain = np.nan_to_num(rain_m, nan=0.0).astype(np.float32)
    effective = rain * RUNOFF_COEFF

    # Depression capacity relative to filled surface
    filled_approx = ndimage.maximum_filter(np.nan_to_num(dem_f, nan=np.nanmedian(dem_f)), size=FOCAL_WIN)
    sink_cap = np.maximum(filled_approx - dem_f, 0.0).astype(np.float32)

    # Local relative-elevation bathtub
    focal_min = ndimage.minimum_filter(np.nan_to_num(dem_f, nan=np.nanmax(dem_f)), size=FOCAL_WIN)
    local_bath = np.maximum(effective - (dem_f - focal_min), 0.0)

    # HAND excess: rain ponding above HAND drainage height (simplified)
    hand_excess = np.maximum(effective - np.nan_to_num(hand, nan=0.0) * 0.15, 0.0)

    depth = np.maximum.reduce(
        [
            hand_excess,
            np.minimum(sink_cap, effective),
            local_bath,
        ]
    ).astype(np.float32)
    depth = np.where(np.isfinite(dem_f), depth, np.nan)
    depth = np.where(depth >= MIN_DEPTH_M, depth, 0.0)
    return {"depth_m": depth, "hand": hand, "sink_capacity_m": sink_cap}


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
    vmax = float(vmax or max(np.nanpercentile(depth[np.isfinite(depth) & (depth > 0)], 98) if np.any(depth > 0) else 0.1, 0.05))
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
    rain = _reproject_to(rain_path, dem.shape, transform, crs)
    # rain is mm in our products — convert
    rain_mm = rain.astype(np.float32)
    # detect units: if max > 5 assume mm
    rain_m = rain_mm / 1000.0 if np.nanmax(rain_mm) > 5 else rain_mm

    layers = compute_hand_bathtub(dem, rain_m, transform)
    depth = layers["depth_m"]

    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    tif = out_dir / f"depth_{borough_id}_{forcing_id}_storm_total_m.tif"
    png = assets_dir / f"depth_{borough_id}_{forcing_id}_storm_total_m.png"
    _write_tif(tif, depth, transform, crs)
    _write_tif(out_dir / f"hand_{borough_id}.tif", layers["hand"], transform, crs)
    _write_png(png, depth)

    meta = {
        "borough_id": borough_id,
        "forcing_id": forcing_id,
        "engine": "pysheds_hand_bathtub_v2",
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "runoff_coeff": RUNOFF_COEFF,
        "bounds": bounds,
        "shape": list(depth.shape),
        "max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
        "mean_wet_m": float(np.nanmean(depth[depth > MIN_DEPTH_M])) if np.any(depth > MIN_DEPTH_M) else 0.0,
        "wet_fraction": float(np.mean(depth > MIN_DEPTH_M)),
        "tif": str(tif),
        "png": png.name,
        "honesty": "Research borough spike (pysheds). NOT official NWS. SFINCS/LISFLOOD-FP blocked without binaries.",
    }
    (out_dir / f"depth_{borough_id}_{forcing_id}_meta.json").write_text(json.dumps(meta, indent=2))
    (assets_dir / f"depth_{borough_id}_{forcing_id}_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
