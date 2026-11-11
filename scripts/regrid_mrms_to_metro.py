#!/usr/bin/env python3
"""Regrid MRMS QPE Ida storm-total + lead frames onto the metro DEM grid.

Spatial bilinear reproject only — never replaces the field with a domain-mean.
Writes under data/processed/mrms_qpe_metro/ and mirrors key files for inundation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from nyc_flash_flood_case_study.config import PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

# Prefer ~30 m HAND/product working grid; fall back to native 10 m metro DEM.
_DEM_WORK = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif"
_DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
DEM = _DEM_WORK if _DEM_WORK.exists() else _DEM_10M
OUT_DIR = PROCESSED_DIR / "mrms_qpe_metro"
PREC = PROCESSED_DIR / "earth2_precip"
MRMS = PROCESSED_DIR / "mrms_qpe"

# Prefer exported Earth2-precip-named MRMS clips; fall back to raw MRMS dir.
SOURCES = {
    "storm_total": [
        PREC / "mrms_qpe_ida_precip_storm_total.tif",
        MRMS / "mrms_qpe_storm_total.tif",
    ],
    "lead_06h": [
        PREC / "mrms_qpe_ida_precip_lead_06h.tif",
        MRMS / "mrms_qpe_lead_06h_citywide.tif",
        MRMS / "mrms_qpe_lead_06h.tif",
    ],
    "lead_12h": [
        PREC / "mrms_qpe_ida_precip_lead_12h.tif",
        MRMS / "mrms_qpe_lead_12h_citywide.tif",
        MRMS / "mrms_qpe_lead_12h.tif",
    ],
    "lead_18h": [
        PREC / "mrms_qpe_ida_precip_lead_18h.tif",
        MRMS / "mrms_qpe_lead_18h_citywide.tif",
        MRMS / "mrms_qpe_lead_18h.tif",
    ],
    "lead_24h": [
        PREC / "mrms_qpe_ida_precip_lead_24h.tif",
        MRMS / "mrms_qpe_lead_24h_citywide.tif",
        MRMS / "mrms_qpe_lead_24h.tif",
    ],
}


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _regrid(src_path: Path, dem_ds: rasterio.io.DatasetReader) -> np.ndarray:
    dst = np.full((dem_ds.height, dem_ds.width), np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        reproject(
            source=data,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dem_ds.transform,
            dst_crs=dem_ds.crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    return dst


def main() -> dict:
    if not DEM.exists():
        raise FileNotFoundError(f"Metro DEM missing — run scripts/fetch_metro_dem.py first: {DEM}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "dem": str(DEM),
        "extent": "metro",
        "bounds": EXTENTS["metro"]["bounds"],
        "method": "bilinear_reproject_to_dem_grid",
        "uniform_mean_forbidden": True,
        "layers": {},
    }

    with rasterio.open(DEM) as dem_ds:
        profile = {
            "driver": "GTiff",
            "height": dem_ds.height,
            "width": dem_ds.width,
            "count": 1,
            "dtype": "float32",
            "crs": dem_ds.crs,
            "transform": dem_ds.transform,
            "nodata": -9999.0,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }
        for key, candidates in SOURCES.items():
            src = _first_existing(candidates)
            if src is None:
                meta["layers"][key] = {"status": "missing"}
                continue
            arr = _regrid(src, dem_ds)
            out = OUT_DIR / f"mrms_qpe_metro_{key}.tif"
            with rasterio.open(out, "w", **profile) as dst:
                dst.write(np.where(np.isfinite(arr), arr, -9999.0), 1)
                dst.update_tags(source=str(src), regrid="bilinear_to_metro_dem")
            finite = np.isfinite(arr) & (arr > 0)
            meta["layers"][key] = {
                "status": "ok",
                "source": str(src),
                "path": str(out),
                "shape": list(arr.shape),
                "mean_pos_mm": float(arr[finite].mean()) if finite.any() else None,
                "max_mm": float(arr[finite].max()) if finite.any() else None,
                "cv": float(arr[finite].std() / arr[finite].mean()) if finite.any() else None,
            }
            print(json.dumps({"layer": key, **meta["layers"][key]}, indent=2))

    (OUT_DIR / "mrms_qpe_metro_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    main()
