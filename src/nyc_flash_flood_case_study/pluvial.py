"""Pluvial flood screening from terrain + imperviousness (not inundation depth)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from .config import EVENT_OUTPUTS, FIGURES_DIR, LANDCOVER_DATASETS, PROCESSED_DIR, PROJECT_ROOT, TERRAIN_DATASETS
from .extents import EXTENTS


def _find_impervious() -> Path | None:
    candidates = [
        LANDCOVER_DATASETS["impervious"],
        PROJECT_ROOT / "legacy_projects_data" / "raw" / "landcover" / "impervious_surface.tif",
        PROJECT_ROOT / "data" / "raw" / "landcover" / "impervious_surface.tif",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _find_terrain_screening() -> Path | None:
    candidates = [
        EVENT_OUTPUTS["terrain_screening_highres"],
        PROCESSED_DIR / "terrain_screening_10m.tif",
        PROJECT_ROOT / "legacy_projects_data" / "processed" / "flash_flood_susceptibility.tif",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def build_pluvial_screening(
    extent_id: str = "south_queens",
    display_shape: tuple[int, int] = (220, 480),
    assets_dir: Path | None = None,
) -> dict:
    """Combine relative terrain screening with imperviousness into a pluvial index.

    Output is a **screening index** in [0, 1], not water depth or flood probability.
    """
    assets_dir = assets_dir or (FIGURES_DIR / "product_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    processed = PROCESSED_DIR / "pluvial"
    processed.mkdir(parents=True, exist_ok=True)

    bounds = EXTENTS[extent_id]["bounds"]
    transform = from_bounds(
        bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"], display_shape[1], display_shape[0]
    )

    terrain_path = _find_terrain_screening()
    impervious_path = _find_impervious()
    if terrain_path is None and impervious_path is None:
        raise FileNotFoundError("Need terrain screening and/or impervious raster for pluvial screening.")

    height, width = display_shape
    terrain = np.zeros((height, width), dtype=np.float32)
    impervious = np.zeros((height, width), dtype=np.float32)
    sources = []

    if terrain_path is not None:
        with rasterio.open(terrain_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=terrain,
                src_transform=src.transform,
                src_crs=src.crs or "EPSG:4326",
                dst_transform=transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
            )
        sources.append(str(terrain_path))
        finite = np.isfinite(terrain)
        if finite.any():
            tmin, tmax = float(np.nanmin(terrain[finite])), float(np.nanmax(terrain[finite]))
            terrain = np.clip((terrain - tmin) / max(tmax - tmin, 1e-6), 0, 1)

    if impervious_path is not None:
        with rasterio.open(impervious_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=impervious,
                src_transform=src.transform,
                src_crs=src.crs or "EPSG:4326",
                dst_transform=transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
            )
        sources.append(str(impervious_path))
        finite = np.isfinite(impervious)
        if finite.any():
            vals = impervious[finite]
            # NLCD-like percent or 0-1
            if float(np.nanmax(vals)) > 1.5:
                impervious = np.clip(impervious / 100.0, 0, 1)
            else:
                impervious = np.clip(impervious, 0, 1)

    # Pluvial screening: low/flat terrain + impervious cover favor street flooding risk
    pluvial = np.clip(0.55 * terrain + 0.45 * impervious, 0, 1).astype(np.float32)
    tif_path = processed / f"pluvial_screening_{extent_id}.tif"
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
        "compress": "deflate",
    }
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(pluvial), pluvial, -9999.0), 1)

    rgba = colormaps["YlOrRd"](pluvial, bytes=True)
    rgba[..., 3] = np.where(pluvial > 0.05, np.minimum(200, (60 + pluvial * 160)).astype(np.uint8), 0)
    png_path = assets_dir / "pluvial_screening.png"
    Image.fromarray(rgba, mode="RGBA").save(png_path, optimize=True)

    meta = {
        "label": "Pluvial screening index",
        "disclaimer": (
            "Relative screening from terrain low/flatness and imperviousness only. "
            "Not inundation depth, not a flood warning, not a calibrated hydrology model."
        ),
        "formula": "0.55 * terrain_screening + 0.45 * imperviousness",
        "png": png_path.name,
        "tif": str(tif_path),
        "extent_id": extent_id,
        "sources": sources,
        "bounds": [[bounds["ymin"], bounds["xmin"]], [bounds["ymax"], bounds["xmax"]]],
        "mean": float(np.nanmean(pluvial)),
        "p90": float(np.nanpercentile(pluvial, 90)),
    }
    (assets_dir / "pluvial_meta.json").write_text(json.dumps(meta, indent=2))
    return meta
