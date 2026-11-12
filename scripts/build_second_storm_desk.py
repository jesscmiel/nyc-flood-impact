#!/usr/bin/env python3
"""Second-storm Decision Desk path (Tropical Storm Henri remnants, Aug 2021).

When MRMS hours are fetchable, builds:
  - data/processed/mrms_qpe_metro_henri/ storm-total (+ optional cum leads)
  - data/processed/inundation/depth_metro_mrms_qpe_henri_storm_total_m.tif
  - figures/product_assets/decision_desk_assets_henri.{json,geojson}

Reuses cached metro HAND + sink capacity + drainage capacity proxy from Ida.
If MRMS fetch fails, writes a documented unavailable stub and leaves Ida as sole event.

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
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DEFAULT_EVENT_DURATION_HR,
    EFFECTIVE_DRAINAGE_HOURS,
    capacity_mm_hr,
    default_drain_candidate_paths,
    drain_coverage_fraction,
    drain_density_norm,
    effective_sink_mm,
    load_drain_points,
    load_impervious_fraction,
)
from flood_risk.inundation.hand_bathtub import MIN_DEPTH_M, depth_from_rain  # noqa: E402
from flood_risk.risk.ranked_assets import build_ranked_assets, write_ranked_assets  # noqa: E402
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402
from nyc_flash_flood_case_study.mrms_qpe_qa import QPE_PRODUCT, fetch_hourly_qpe  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
MRMS_OUT = PROCESSED_DIR / "mrms_qpe_metro_henri"
BOUNDS = EXTENTS[PRIMARY_DATA_EXTENT]["bounds"]

# Henri remnants — NYC rain concentrated ~2021-08-21 evening into 08-22.
INIT = datetime(2021, 8, 21, 18, 0, tzinfo=timezone.utc)
LEAD_MAX = 24
CUM_LEADS = (6, 12, 18, 24)

_DEM_WORK = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif"
_DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
DEM = _DEM_WORK if _DEM_WORK.exists() else _DEM_10M


def _decode_metro_crop(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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


def _write_tif(path: Path, data: np.ndarray, transform, crs) -> None:
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
        compress="deflate",
        nodata=np.nan,
    ) as dst:
        dst.write(data.astype(np.float32), 1)


def _load_land(shape, transform) -> np.ndarray:
    mask = PROCESSED_DIR / "land_mask_metro.tif"
    if not mask.exists():
        return np.ones(shape, dtype=bool)
    with rasterio.open(mask) as ms:
        data = ms.read(1)
        if data.shape == shape and ms.transform == transform:
            return data > 0
        dst = np.zeros(shape, dtype=np.float32)
        reproject(
            source=data.astype(np.float32),
            destination=dst,
            src_transform=ms.transform,
            src_crs=ms.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
        )
        return dst > 0


def _write_unavailable(reason: str) -> dict:
    meta = {
        "event_id": "henri-2021",
        "available": False,
        "reason": reason,
        "init_time_utc": INIT.isoformat(),
        "lead_hours_max": LEAD_MAX,
        "honesty": "Second storm desk unavailable — Ida remains the only loaded Decision Desk event.",
    }
    out = ASSETS / "second_storm_henri_meta.json"
    out.write_text(json.dumps(meta, indent=2))
    (OUTPUTS_DIR / "second_storm_henri_meta.json").write_text(out.read_text())
    return meta


def fetch_henri_mrms() -> dict:
    if not DEM.exists():
        return _write_unavailable(f"missing DEM {DEM}")
    MRMS_OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(DEM) as dem_ds:
        cum = np.zeros((dem_ds.height, dem_ds.width), dtype=np.float32)
        hours_ok: list[int] = []
        errors: list[str] = []
        for lead in range(0, LEAD_MAX + 1):
            ts = INIT + timedelta(hours=lead)
            try:
                grib = fetch_hourly_qpe(ts)
                crop, lat, lon = _decode_metro_crop(grib)
                grid = _to_dem_grid(crop, lat, lon, dem_ds)
                hour_path = MRMS_OUT / f"mrms_qpe_metro_henri_1h_lead_{lead:02d}h.tif"
                _write_tif(hour_path, grid, dem_ds.transform, dem_ds.crs)
                cum = cum + np.nan_to_num(grid, nan=0.0)
                hours_ok.append(lead)
                if lead in CUM_LEADS:
                    _write_tif(
                        MRMS_OUT / f"mrms_qpe_metro_henri_cum_lead_{lead:02d}h.tif",
                        cum,
                        dem_ds.transform,
                        dem_ds.crs,
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"+{lead}h: {exc}")
        if len(hours_ok) < 6:
            return _write_unavailable(
                f"too few Henri MRMS hours ({len(hours_ok)}); errors={errors[:5]}"
            )
        total_path = MRMS_OUT / "mrms_qpe_metro_henri_storm_total.tif"
        _write_tif(total_path, cum, dem_ds.transform, dem_ds.crs)
        meta = {
            "event_id": "henri-2021",
            "available": True,
            "product": QPE_PRODUCT,
            "init_time_utc": INIT.isoformat(),
            "hours_ok": hours_ok,
            "n_hours": len(hours_ok),
            "storm_total_max_mm": float(np.nanmax(cum)),
            "storm_total_tif": str(total_path),
            "errors_sample": errors[:8],
        }
        (MRMS_OUT / "meta.json").write_text(json.dumps(meta, indent=2))
        return meta


def build_henri_depth(mrms_meta: dict) -> dict:
    hand_p = INUN / "hand_metro.tif"
    sink_p = INUN / "sink_capacity_metro_m.tif"
    if not hand_p.exists() or not sink_p.exists():
        return _write_unavailable("missing hand_metro / sink_capacity — run build_metro_inundation.py first")
    rain_p = Path(mrms_meta["storm_total_tif"])
    with rasterio.open(DEM) as dem_ds, rasterio.open(hand_p) as hs, rasterio.open(sink_p) as ss, rasterio.open(rain_p) as rs:
        dem = dem_ds.read(1).astype(np.float32)
        hand = hs.read(1).astype(np.float32)
        sink = ss.read(1).astype(np.float32)
        rain = rs.read(1).astype(np.float32)
        transform, crs = dem_ds.transform, dem_ds.crs
        shape = dem.shape
    # Cached HAND GeoTIFF uses -9999 nodata as a real float; treat as NaN or depths explode.
    hand = np.where((hand <= -1000) | ~np.isfinite(hand), np.nan, hand).astype(np.float32)
    sink = np.where((sink < 0) | ~np.isfinite(sink), 0.0, sink).astype(np.float32)
    rain = np.where(~np.isfinite(rain) | (rain < 0), 0.0, rain).astype(np.float32)
    land = _load_land(shape, transform)

    nlcd = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
    if nlcd.exists():
        impervious = load_impervious_fraction(shape, transform, crs, nlcd)
        drain_pts, _, _ = load_drain_points(
            default_drain_candidate_paths(
                RAW_DIR / "infrastructure",
                ASSETS,
                FIGURES_DIR / "ida_v0_assets",
                RAW_DIR,
            )
        )
        drain_norm = drain_density_norm(shape, transform, drain_pts)
        capacity = capacity_mm_hr(impervious, drain_norm)
        _, excess, _ = effective_sink_mm(
            rain,
            capacity,
            duration_hr=max(DEFAULT_EVENT_DURATION_HR, float(LEAD_MAX)),
            drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
        )
        drain_cov = drain_coverage_fraction(drain_norm, land)
    else:
        excess = rain
        drain_cov = None

    depth = depth_from_rain(excess, hand, sink, dem)
    depth = np.where(land, depth, np.nan).astype(np.float32)
    depth = np.where(np.isfinite(depth) & (depth >= MIN_DEPTH_M), depth, np.nan)

    out_tif = INUN / "depth_metro_mrms_qpe_henri_storm_total_m.tif"
    _write_tif(out_tif, depth, transform, crs)

    lead_tifs: list[tuple[float, Path]] = []
    for lead in CUM_LEADS:
        cum_rain_p = MRMS_OUT / f"mrms_qpe_metro_henri_cum_lead_{lead:02d}h.tif"
        if not cum_rain_p.exists():
            continue
        with rasterio.open(cum_rain_p) as crs_ds:
            cum_rain = crs_ds.read(1).astype(np.float32)
        if nlcd.exists():
            _, excess_l, _ = effective_sink_mm(
                cum_rain,
                capacity,
                duration_hr=max(DEFAULT_EVENT_DURATION_HR, float(lead)),
                drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
            )
        else:
            excess_l = cum_rain
        d = depth_from_rain(excess_l, hand, sink, dem)
        d = np.where(land, d, np.nan).astype(np.float32)
        d = np.where(np.isfinite(d) & (d >= MIN_DEPTH_M), d, np.nan)
        lead_tif = INUN / f"depth_metro_mrms_henri_cum_lead_{lead:02d}h_m.tif"
        _write_tif(lead_tif, d, transform, crs)
        lead_tifs.append((float(lead), lead_tif))

    return {
        "depth_tif": str(out_tif),
        "lead_tifs": [(h, str(p)) for h, p in lead_tifs],
        "wet_fraction": float(np.mean(np.isfinite(depth))),
        "max_depth_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
        "drain_coverage": drain_cov,
    }


def build_henri_desk(depth_meta: dict) -> dict:
    gpkg = ASSETS / "exposure_citywide.gpkg"
    depth = Path(depth_meta["depth_tif"])
    lead_tifs = [(h, Path(p)) for h, p in depth_meta.get("lead_tifs") or []]
    payload = build_ranked_assets(
        gpkg=gpkg,
        depth_tif=depth,
        lead_tifs=lead_tifs,
        top_n=None,
        engine_id="pysheds_hand_bathtub_v2",
        engine_role="primary_research_depth",
        engine_label="pysheds HAND/bathtub (metro · MRMS QPE Henri)",
        access_fixture=None,
    )
    payload["scenario"] = {
        "id": "henri_mrms_metro",
        "label": "Henri · MRMS QPE · NYC metro (research)",
        "case_study": "Tropical Storm Henri remnants 2021-08-21/22",
        "forcing": "mrms_qpe_henri_spatial",
    }
    out_json = ASSETS / "decision_desk_assets_henri.json"
    out_geo = ASSETS / "decision_desk_assets_henri.geojson"
    write_ranked_assets(payload, out_json, out_geo)
    (OUTPUTS_DIR / "decision_desk_assets_henri.json").write_text(out_json.read_text())
    return {
        "assets_json": out_json.name,
        "assets_geojson": out_geo.name,
        "wet_total": payload["counts"]["wet_total"],
        "top": [
            {"name": a["name"], "cm": a["max_depth_cm"], "band": a["band_label"], "lead_h": a["first_exceedance_lead_h"]}
            for a in payload["assets"][:5]
        ],
    }


def patch_manifests(henri_meta: dict, desk_meta: dict | None) -> None:
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["second_storm"] = {
            "event_id": "henri-2021",
            "available": bool(henri_meta.get("available")),
            "meta": "second_storm_henri_meta.json",
            "desk": desk_meta,
            "honesty": henri_meta.get("honesty")
            or "Research Henri desk — NOT peer-calibrated to Ida talk track.",
        }
        desk = m.setdefault("asset_decision_desk", {})
        if desk_meta and henri_meta.get("available"):
            desk["events"] = {
                "ida-2021": {
                    "assets_json": "decision_desk_assets.json",
                    "assets_geojson": "decision_desk_assets.geojson",
                },
                "henri-2021": {
                    "assets_json": desk_meta["assets_json"],
                    "assets_geojson": desk_meta["assets_geojson"],
                },
            }
        mp.write_text(json.dumps(m, indent=2))


def main() -> dict:
    print("Fetching Henri MRMS QPE (metro)…")
    mrms_meta = fetch_henri_mrms()
    if not mrms_meta.get("available"):
        patch_manifests(mrms_meta, None)
        print(json.dumps(mrms_meta, indent=2))
        return mrms_meta

    print("Building Henri depth on cached metro HAND…")
    depth_meta = build_henri_depth(mrms_meta)
    if "depth_tif" not in depth_meta:
        patch_manifests(depth_meta, None)
        print(json.dumps(depth_meta, indent=2))
        return depth_meta

    print("Building Henri Decision Desk assets…")
    desk_meta = build_henri_desk(depth_meta)
    henri_meta = {
        "event_id": "henri-2021",
        "available": True,
        "init_time_utc": INIT.isoformat(),
        "mrms": mrms_meta,
        "depth": depth_meta,
        "desk": desk_meta,
        "honesty": (
            "Tropical Storm Henri research desk via MRMS×HAND — NOT NWS / NOT decision-grade. "
            "Lead chips use 6/12/18/24h cum frames for this event."
        ),
    }
    out = ASSETS / "second_storm_henri_meta.json"
    out.write_text(json.dumps(henri_meta, indent=2))
    (OUTPUTS_DIR / "second_storm_henri_meta.json").write_text(out.read_text())
    patch_manifests(henri_meta, desk_meta)
    print(json.dumps(henri_meta, indent=2, default=str)[:4000])
    return henri_meta


if __name__ == "__main__":
    main()
