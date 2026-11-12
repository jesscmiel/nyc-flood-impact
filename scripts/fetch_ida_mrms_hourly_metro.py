#!/usr/bin/env python3
"""Fetch native hourly MRMS MultiSensor QPE for Ida and regrid to metro DEM.

Writes under data/processed/mrms_qpe_metro/:
  - mrms_qpe_metro_1h_lead_{LL}h.tif  — 1 h QPE ending at init+LL
  - mrms_qpe_metro_cum_lead_{LL}h.tif — cumulative sum from lead 0…LL
  - mrms_qpe_metro_storm_total.tif    — cum at +36 h (full window)
  - mrms_qpe_metro_lead_{06,12,18,24}h.tif — legacy 6 h interval sums (compat)

Init = 2021-09-01T12:00 UTC; leads 0…36 inclusive.
Research only — NOT NWS / NOT decision-grade.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nyc_flash_flood_case_study.config import PROCESSED_DIR, PROJECT_ROOT  # noqa: E402
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402
from nyc_flash_flood_case_study.mrms_qpe_qa import (  # noqa: E402
    QPE_PRODUCT,
    fetch_hourly_qpe,
)

_DEM_WORK = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif"
_DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
DEM = _DEM_WORK if _DEM_WORK.exists() else _DEM_10M
OUT_DIR = PROCESSED_DIR / "mrms_qpe_metro"
BOUNDS = EXTENTS[PRIMARY_DATA_EXTENT]["bounds"]
INIT = datetime(2021, 9, 1, 12, 0, tzinfo=timezone.utc)
LEAD_MIN = 0
LEAD_MAX = 36
LEGACY_INTERVAL_LEADS = (6, 12, 18, 24)


def _decode_metro_crop(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode QPE GRIB and crop to metro bbox (wider than south-Queens study crop)."""
    import gzip
    import shutil
    import tempfile

    import xarray as xr

    with gzip.open(path, "rb") as compressed, tempfile.NamedTemporaryFile(suffix=".grib2") as raw:
        shutil.copyfileobj(compressed, raw)
        raw.flush()
        dataset = xr.open_dataset(raw.name, engine="cfgrib", backend_kwargs={"indexpath": ""})
        try:
            variable = dataset[next(iter(dataset.data_vars))]
            values = variable.values.astype(np.float32)
            missing = float(variable.attrs.get("GRIB_missingValue", 3.4028235e38))
            values = np.where((values >= missing * 0.1) | ~np.isfinite(values), np.nan, values)
            latitude = dataset["latitude"].values.astype(np.float64)
            longitude = dataset["longitude"].values.astype(np.float64)
        finally:
            dataset.close()

    longitude = np.where(longitude > 180.0, longitude - 360.0, longitude)
    lat_idx = np.flatnonzero(
        (latitude >= BOUNDS["ymin"] - 0.08) & (latitude <= BOUNDS["ymax"] + 0.08)
    )
    lon_idx = np.flatnonzero(
        (longitude >= BOUNDS["xmin"] - 0.08) & (longitude <= BOUNDS["xmax"] + 0.08)
    )
    if lat_idx.size == 0 or lon_idx.size == 0:
        raise ValueError(f"No MRMS QPE cells intersect metro domain in {path.name}")
    crop = values[np.ix_(lat_idx, lon_idx)]
    return crop, latitude[lat_idx], longitude[lon_idx]


def _to_dem_grid(field: np.ndarray, lat: np.ndarray, lon: np.ndarray, dem_ds) -> np.ndarray:
    if lat[0] < lat[-1]:
        field = field[::-1, :]
        lat = lat[::-1]
    src_transform = from_bounds(
        float(lon.min()),
        float(lat.min()),
        float(lon.max()),
        float(lat.max()),
        field.shape[1],
        field.shape[0],
    )
    dst = np.full((dem_ds.height, dem_ds.width), np.nan, dtype=np.float32)
    reproject(
        source=field.astype(np.float32),
        destination=dst,
        src_transform=src_transform,
        src_crs="EPSG:4326",
        dst_transform=dem_ds.transform,
        dst_crs=dem_ds.crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return dst


def _write(path: Path, data: np.ndarray, profile: dict, **tags) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})


def main() -> dict:
    if not DEM.exists():
        raise FileNotFoundError(f"Metro DEM missing: {DEM}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    leads = list(range(LEAD_MIN, LEAD_MAX + 1))
    hourly: dict[int, np.ndarray] = {}
    meta = {
        "product": QPE_PRODUCT,
        "source": "https://noaa-mrms-pds.s3.amazonaws.com/",
        "init_time_utc": INIT.strftime("%Y-%m-%dT%H:%M"),
        "extent": PRIMARY_DATA_EXTENT,
        "bounds": BOUNDS,
        "dem": str(DEM),
        "lead_hours_min": LEAD_MIN,
        "lead_hours_max": LEAD_MAX,
        "native_step_h": 1,
        "method": "native_hourly_mrms_qpe_bilinear_to_metro_dem",
        "frames": [],
        "legacy_interval_leads": list(LEGACY_INTERVAL_LEADS),
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

        for lead in leads:
            end = INIT + timedelta(hours=lead)
            path = fetch_hourly_qpe(end)
            crop, lat, lon = _decode_metro_crop(path)
            field = _to_dem_grid(crop, lat, lon, dem_ds)
            hourly[lead] = field
            out_1h = OUT_DIR / f"mrms_qpe_metro_1h_lead_{lead:02d}h.tif"
            _write(
                out_1h,
                field,
                profile,
                lead_hours=lead,
                valid_time=end.strftime("%Y-%m-%dT%H:%M"),
                accumulation="1h_ending_at_valid",
                native="true",
            )
            finite = np.isfinite(field)
            meta["frames"].append(
                {
                    "lead_hours": lead,
                    "valid_time": end.strftime("%Y-%m-%dT%H:%M"),
                    "path_1h": str(out_1h),
                    "max_mm": float(np.nanmax(field)) if finite.any() else None,
                    "mean_mm": float(np.nanmean(field)) if finite.any() else None,
                    "source_file": path.name,
                }
            )
            print(
                json.dumps(
                    {
                        "lead": lead,
                        "valid": end.strftime("%Y-%m-%dT%H:%M"),
                        "max_mm": meta["frames"][-1]["max_mm"],
                        "mean_mm": meta["frames"][-1]["mean_mm"],
                    }
                )
            )

        cum = np.zeros((dem_ds.height, dem_ds.width), dtype=np.float32)
        for lead in leads:
            cum = cum + np.nan_to_num(hourly[lead], nan=0.0)
            out_cum = OUT_DIR / f"mrms_qpe_metro_cum_lead_{lead:02d}h.tif"
            _write(
                out_cum,
                cum,
                profile,
                lead_hours=lead,
                accumulation="storm_cumulative_from_init",
            )
            meta["frames"][lead]["path_cum"] = str(out_cum)
            meta["frames"][lead]["cum_max_mm"] = float(np.nanmax(cum))
            meta["frames"][lead]["cum_mean_mm"] = float(np.nanmean(cum))

        # Storm total = full 0–36h cumulative
        _write(
            OUT_DIR / "mrms_qpe_metro_storm_total.tif",
            cum,
            profile,
            accumulation="storm_cumulative_0_36h",
        )
        meta["storm_total"] = {
            "path": str(OUT_DIR / "mrms_qpe_metro_storm_total.tif"),
            "max_mm": float(np.nanmax(cum)),
            "mean_mm": float(np.nanmean(cum)),
            "lead_hours": LEAD_MAX,
        }

        # Legacy 6 h interval fields (sum of native hours in (prev, lead]) for older tools
        prev = 0
        for lead in LEGACY_INTERVAL_LEADS:
            interval = np.zeros((dem_ds.height, dem_ds.width), dtype=np.float32)
            for h in range(prev + 1, lead + 1):
                interval = interval + np.nan_to_num(hourly[h], nan=0.0)
            out = OUT_DIR / f"mrms_qpe_metro_lead_{lead:02d}h.tif"
            _write(out, interval, profile, accumulation=f"interval_{prev+1}_to_{lead}h")
            meta.setdefault("legacy_intervals", {})[f"lead_{lead:02d}h"] = {
                "path": str(out),
                "max_mm": float(np.nanmax(interval)),
                "hours": list(range(prev + 1, lead + 1)),
            }
            prev = lead

    (OUT_DIR / "mrms_qpe_metro_hourly_meta.json").write_text(json.dumps(meta, indent=2))
    # Keep generic meta pointer current
    (OUT_DIR / "mrms_qpe_metro_meta.json").write_text(
        json.dumps(
            {
                "dem": str(DEM),
                "extent": PRIMARY_DATA_EXTENT,
                "bounds": BOUNDS,
                "method": meta["method"],
                "hourly_meta": str(OUT_DIR / "mrms_qpe_metro_hourly_meta.json"),
                "lead_hours_min": LEAD_MIN,
                "lead_hours_max": LEAD_MAX,
                "n_native_hourly": len(leads),
                "storm_total": meta["storm_total"],
            },
            indent=2,
        )
    )
    print(json.dumps({"n_hourly": len(leads), "storm_total_max_mm": meta["storm_total"]["max_mm"]}, indent=2))
    return meta


if __name__ == "__main__":
    main()
