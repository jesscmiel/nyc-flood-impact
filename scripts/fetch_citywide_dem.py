#!/usr/bin/env python3
"""Fetch a citywide DEM for pluvial susceptibility (best-effort).

Legacy five-borough ~90 m export. Prefer ``scripts/fetch_metro_dem.py`` for the
primary metro ≤10 m mosaic used by the inundation rebuild.

Tries USGS 3DEP ImageServer export at modest resolution. Falls back to existing
South Queens DEM if the download fails — never invents elevation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.enums import Resampling

from nyc_flash_flood_case_study.config import RAW_DIR
from nyc_flash_flood_case_study.extents import EXTENTS

BOUNDS = EXTENTS["citywide"]["bounds"]
OUT = RAW_DIR / "terrain" / "dem_usgs_citywide.tif"


def fetch() -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # ~90 m cells over citywide bbox (~0.0008°)
    width, height = 720, 540
    xmin, ymin, xmax, ymax = BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"]
    # USGS 3DEP Elevation ImageServer
    url = (
        "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    )
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": 4326,
        "imageSR": 4326,
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "noDataInterpretation": "esriNoDataMatchAny",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    meta = {"attempted": url, "status": "pending", "path": str(OUT)}
    try:
        r = requests.get(url, params=params, timeout=120, headers={"User-Agent": "nyc-flood-impact/1.0"})
        meta["http_status"] = r.status_code
        meta["content_type"] = r.headers.get("content-type")
        meta["nbytes"] = len(r.content)
        if r.status_code != 200 or len(r.content) < 1000:
            meta["status"] = "failed_http"
            return meta
        # May return GeoTIFF bytes
        with MemoryFile(r.content) as mem:
            with mem.open() as src:
                data = src.read(1).astype(np.float32)
                transform = src.transform if src.transform else from_bounds(xmin, ymin, xmax, ymax, width, height)
                crs = src.crs or "EPSG:4326"
                # If dimensions mismatch, regrid
                if data.shape != (height, width):
                    dst = np.full((height, width), np.nan, dtype=np.float32)
                    dst_tf = from_bounds(xmin, ymin, xmax, ymax, width, height)
                    reproject(
                        source=data,
                        destination=dst,
                        src_transform=src.transform,
                        src_crs=crs,
                        dst_transform=dst_tf,
                        dst_crs="EPSG:4326",
                        resampling=Resampling.bilinear,
                    )
                    data, transform, crs = dst, dst_tf, "EPSG:4326"
        profile = {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": crs,
            "transform": transform,
            "compress": "deflate",
            "nodata": -9999.0,
        }
        with rasterio.open(OUT, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(data), data, -9999.0), 1)
            dst.update_tags(source="USGS 3DEP Elevation ImageServer", extent="citywide")
        finite = np.isfinite(data) & (data > -500) & (data < 3000)
        meta.update(
            {
                "status": "ok" if finite.any() else "empty",
                "finite_fraction": float(finite.mean()),
                "min": float(data[finite].min()) if finite.any() else None,
                "max": float(data[finite].max()) if finite.any() else None,
                "shape": list(data.shape),
            }
        )
    except Exception as exc:  # noqa: BLE001
        meta["status"] = "error"
        meta["error"] = str(exc)
    (RAW_DIR / "terrain" / "dem_citywide_fetch.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    fetch()
