#!/usr/bin/env python3
"""Build open drainage/sewer capacity proxy rasters + loose Ida/311 calibration notes.

Uses NLCD impervious + optional OSM/open drain points + literature mm/hr sink.
NOT a DEP sewer model. Writes data/processed/drainage_capacity/ and product assets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DEFAULT_EVENT_DURATION_HR,
    EFFECTIVE_DRAINAGE_HOURS,
    ENGINE_ID,
    apply_capacity_to_rate_mm_hr,
    capacity_mm_hr,
    drain_density_norm,
    effective_sink_mm,
    load_drain_points,
    load_impervious_fraction,
    param_meta,
)
from flood_risk.validate.scores import score_points_on_depth  # noqa: E402
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from nyc_flash_flood_case_study.extents import PRIMARY_DATA_EXTENT  # noqa: E402

OUT = PROCESSED_DIR / "drainage_capacity"
ASSETS = FIGURES_DIR / "product_assets"
DEM_WORK = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif"
DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
DEM = DEM_WORK if DEM_WORK.exists() else DEM_10M
NLCD = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
MRMS = PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif"
INUN = PROCESSED_DIR / "inundation"


def _write_tif(path: Path, data: np.ndarray, transform, crs, nodata: float = -9999.0) -> None:
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
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(np.where(np.isfinite(data), data, nodata).astype(np.float32), 1)


def _rgba(data: np.ndarray, land: np.ndarray, cmap: str, vmax: float) -> np.ndarray:
    finite = np.isfinite(data) & land & (data > 0)
    norm = np.clip(np.where(np.isfinite(data), data, 0.0) / max(vmax, 1e-6), 0, 1)
    rgba = colormaps[cmap](norm, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(220, 40 + (norm * 180).astype(np.uint8)), 0)
    return rgba


def _stats(arr: np.ndarray, land: np.ndarray) -> dict:
    a = arr[land & np.isfinite(arr)]
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "mean": float(np.mean(a)),
        "p50": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
        "max": float(np.max(a)),
        "min": float(np.min(a)),
    }


def main() -> dict:
    if not DEM.exists():
        raise FileNotFoundError(f"Missing metro DEM: {DEM}")
    if not NLCD.exists():
        raise FileNotFoundError(f"Missing NLCD impervious: {NLCD}")
    if not MRMS.exists():
        raise FileNotFoundError(f"Missing metro MRMS storm-total: {MRMS}")

    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    with rasterio.open(DEM) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        shape = (dem_ds.height, dem_ds.width)

    land_path = PROCESSED_DIR / "land_mask_metro.tif"
    if land_path.exists():
        with rasterio.open(land_path) as ms:
            land = ms.read(1) > 0
            if land.shape != shape:
                land_arr = np.zeros(shape, dtype=np.uint8)
                reproject = __import__("rasterio.warp", fromlist=["reproject"]).reproject
                Resampling = __import__("rasterio.enums", fromlist=["Resampling"]).Resampling
                reproject(
                    source=rasterio.band(ms, 1),
                    destination=land_arr,
                    src_transform=ms.transform,
                    src_crs=ms.crs,
                    dst_transform=transform,
                    dst_crs=crs,
                    resampling=Resampling.nearest,
                )
                land = land_arr > 0
    else:
        land = np.ones(shape, dtype=bool)

    print("Loading NLCD impervious → metro grid…")
    impervious = load_impervious_fraction(shape, transform, crs, NLCD)

    drain_candidates = [
        RAW_DIR / "infrastructure" / "osm_drains_south_queens.geojson",
        ASSETS / "catch_basins.geojson",
        FIGURES_DIR / "ida_v0_assets" / "catch_basins.geojson",
        RAW_DIR / "infrastructure" / "nycdep_catch_basins_south_queens.json",
    ]
    points, drains_path, drains_status = load_drain_points(drain_candidates)
    print(f"Drain points: n={len(points)} status={drains_status} path={drains_path}")
    drain_norm = drain_density_norm(shape, transform, points)

    capacity = capacity_mm_hr(impervious, drain_norm)

    with rasterio.open(MRMS) as src:
        rain = src.read(1).astype(np.float32)
        if src.nodata is not None:
            rain = np.where(rain == src.nodata, np.nan, rain)
        rain = np.where(rain < 0, np.nan, rain)

    sink, excess, efficiency = effective_sink_mm(
        rain,
        capacity,
        duration_hr=DEFAULT_EVENT_DURATION_HR,
        drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
    )
    # Rate field for optional SFINCS forcing
    rate = np.nan_to_num(rain, nan=0.0) / DEFAULT_EVENT_DURATION_HR
    excess_rate, eff_rate = apply_capacity_to_rate_mm_hr(rate, capacity)

    _write_tif(OUT / "impervious_fraction_metro.tif", impervious, transform, crs)
    _write_tif(OUT / "drain_density_norm_metro.tif", drain_norm, transform, crs)
    _write_tif(OUT / "drainage_capacity_mm_hr.tif", capacity, transform, crs)
    _write_tif(OUT / "drainage_sink_mm.tif", sink, transform, crs)
    _write_tif(OUT / "excess_precip_mm.tif", excess, transform, crs)
    _write_tif(OUT / "drainage_efficiency.tif", efficiency, transform, crs)
    _write_tif(OUT / "excess_precip_rate_mm_hr.tif", excess_rate, transform, crs)

    # Preview PNGs
    Image.fromarray(_rgba(capacity, land, "YlGnBu", 25.0), "RGBA").save(
        ASSETS / "drainage_capacity_mm_hr.png", optimize=True
    )
    Image.fromarray(_rgba(excess, land, "OrRd", float(np.nanpercentile(excess[land], 99) or 50)), "RGBA").save(
        ASSETS / "excess_precip_after_drainage_mm.png", optimize=True
    )

    # Loose calibration vs 311 / Ida narrative bands (honest limits)
    # Narrative: Ida street flooding often ankle–knee+ in worst NYC pockets (~0.15–0.6 m+);
    # FloodNet-style bands used as qualitative reference only (no citywide FloodNet grid on disk).
    ida_narrative_bands_m = [
        {"id": "nuisance", "min_m": 0.03, "max_m": 0.08, "note": "curb / nuisance"},
        {"id": "ankle", "min_m": 0.08, "max_m": 0.20, "note": "ankle-deep street"},
        {"id": "knee", "min_m": 0.20, "max_m": 0.45, "note": "knee-deep pockets (Ida narratives)"},
        {"id": "extreme", "min_m": 0.45, "max_m": None, "note": "deep underpasses / basement risk"},
    ]

    depth_drained = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    depth_undrained = INUN / "depth_metro_mrms_undrained_ida_storm_total_m.tif"
    calibration: dict = {
        "method": "loose_spatial_311_plus_ida_narrative_bands",
        "floodnet_citywide_grid": False,
        "dep_sewer_model": False,
        "ida_narrative_bands_m": ida_narrative_bands_m,
        "limits": (
            "311 hit-rates show spatial concentration only — no magnitude skill, no ROC, "
            "no non-flood controls. Narrative depth bands are qualitative Ida reporting "
            "ranges, not FloodNet station calibration (no citywide FloodNet grid on disk). "
            "Drain density uses open OSM inlet/manhole points in South Queens only — "
            "synthetic demo drainage_nodes are excluded; citywide DEP catch-basin SODA "
            "pull was unavailable — capacity falls back to NLCD-modulated base rate "
            "outside those points. Primary HAND depths remain shallow vs Ida narratives."
        ),
    }
    reports = ASSETS / "observed_311.geojson"
    if depth_drained.exists() and reports.exists():
        try:
            cal_d = score_points_on_depth(
                depth_tif=depth_drained,
                reports_geojson=reports,
                gauges_geojson=ASSETS / "nwm_ahps_gauges.geojson",
                depth_hit_m=0.03,
            )
            calibration["with_drainage_proxy"] = {
                "hit_rate_311": cal_d["summary"]["hit_rate_311"],
                "hit_rate_gauges": cal_d["summary"]["hit_rate_gauges"],
                "confidence": cal_d["summary"].get("confidence"),
            }
        except Exception as exc:  # noqa: BLE001
            calibration["with_drainage_proxy_error"] = str(exc)
    if depth_undrained.exists() and reports.exists():
        try:
            cal_u = score_points_on_depth(
                depth_tif=depth_undrained,
                reports_geojson=reports,
                gauges_geojson=ASSETS / "nwm_ahps_gauges.geojson",
                depth_hit_m=0.03,
            )
            calibration["undrained_baseline"] = {
                "hit_rate_311": cal_u["summary"]["hit_rate_311"],
                "hit_rate_gauges": cal_u["summary"]["hit_rate_gauges"],
            }
        except Exception as exc:  # noqa: BLE001
            calibration["undrained_baseline_error"] = str(exc)

    rain_mask = land & np.isfinite(rain) & (rain > 0)
    rain_pos = rain[rain_mask]
    excess_pos = excess[rain_mask]
    sink_on_rain = sink[rain_mask]
    meta = {
        "product": "drainage_capacity_proxy",
        "engine": ENGINE_ID,
        "extent": PRIMARY_DATA_EXTENT,
        "shape": list(shape),
        "dem": str(DEM),
        "nlcd_impervious": str(NLCD),
        "mrms_storm_total": str(MRMS),
        "event_duration_hr": DEFAULT_EVENT_DURATION_HR,
        "effective_drainage_hours": EFFECTIVE_DRAINAGE_HOURS,
        "drain_points": {
            "n": len(points),
            "status": drains_status,
            "path": str(drains_path) if drains_path else None,
            "note": (
                "Open OSM/demo drain nodes only where present. "
                "nycdep_catch_basins_south_queens.json is a SODA error payload — unused."
            ),
        },
        "paths": {
            "impervious_fraction": str(OUT / "impervious_fraction_metro.tif"),
            "drain_density_norm": str(OUT / "drain_density_norm_metro.tif"),
            "capacity_mm_hr": str(OUT / "drainage_capacity_mm_hr.tif"),
            "sink_mm": str(OUT / "drainage_sink_mm.tif"),
            "excess_precip_mm": str(OUT / "excess_precip_mm.tif"),
            "efficiency": str(OUT / "drainage_efficiency.tif"),
            "excess_rate_mm_hr": str(OUT / "excess_precip_rate_mm_hr.tif"),
            "preview_capacity_png": "drainage_capacity_mm_hr.png",
            "preview_excess_png": "excess_precip_after_drainage_mm.png",
        },
        "stats_on_land": {
            "impervious_fraction": _stats(impervious, land),
            "drain_density_norm": _stats(drain_norm, land),
            "capacity_mm_hr": _stats(capacity, land),
            "sink_mm": _stats(sink, land),
            "excess_precip_mm": _stats(excess, land),
            "efficiency": _stats(efficiency, land),
            "mrms_storm_total_mm": _stats(rain, land),
            "fraction_precip_removed_mean": (
                float(np.mean(sink_on_rain) / np.mean(rain_pos))
                if rain_pos.size and np.mean(rain_pos) > 0
                else None
            ),
            "excess_mean_mm_where_rain_pos": float(np.mean(excess_pos)) if excess_pos.size else None,
        },
        "calibration": calibration,
        **param_meta(),
        "disclaimer": (
            "Open drainage capacity proxy only — NOT DEP sewer, NOT SWMM, NOT official NWS. "
            "Reduces effective precip via literature mm/hr sink modulated by NLCD impervious "
            "and sparse open drain density, with surcharge efficiency collapse in extreme rates."
        ),
    }
    (OUT / "drainage_capacity_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "drainage_capacity_meta.json").write_text(json.dumps(meta, indent=2))
    (PROJECT_ROOT / "outputs" / "drainage_capacity_meta.json").write_text(json.dumps(meta, indent=2))

    print(
        json.dumps(
            {
                "engine": ENGINE_ID,
                "drain_points": len(points),
                "capacity_mean_mm_hr": meta["stats_on_land"]["capacity_mm_hr"].get("mean"),
                "excess_mean_mm": meta["stats_on_land"]["excess_precip_mm"].get("mean"),
                "fraction_precip_removed_mean": meta["stats_on_land"]["fraction_precip_removed_mean"],
                "wrote": str(OUT / "drainage_capacity_meta.json"),
            },
            indent=2,
        )
    )
    return meta


if __name__ == "__main__":
    main()
