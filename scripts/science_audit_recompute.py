#!/usr/bin/env python3
"""Recompute flood-modeling science audit checks (validation + magnitude gap).

Research only — NOT certified skill / NOT NWS. Prefer MRMS for Ida precip truth;
Earth2 remains scenario. Writes outputs/science_audit_recompute.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from flood_risk.validate.scores import score_points_on_depth
from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import DEFAULT_MAP_EXTENT, EXTENTS, PRIMARY_DATA_EXTENT

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
PREC_METRO = PROCESSED_DIR / "mrms_qpe_metro"
PREC = PROCESSED_DIR / "earth2_precip"
OUT = PROJECT_ROOT / "outputs" / "science_audit_recompute.json"


def _raster_stats(path: Path, thresholds: tuple[float, ...] = (0.03, 0.05)) -> dict:
    with rasterio.open(path) as ds:
        arr = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            arr = np.where(arr == ds.nodata, np.nan, arr)
        arr = np.where(arr < -100, np.nan, arr)
        finite = np.isfinite(arr)
        wet = arr[finite & (arr > 0.005)]
        out = {
            "path": str(path),
            "shape": list(arr.shape),
            "bounds": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
            "max_m": float(np.nanmax(arr)) if finite.any() else None,
            "p50_wet_m": float(np.percentile(wet, 50)) if wet.size else None,
            "p90_wet_m": float(np.percentile(wet, 90)) if wet.size else None,
        }
        for t in thresholds:
            out[f"wet_fraction_ge_{int(t*100)}cm"] = float(np.nanmean(arr >= t)) if finite.any() else None
        return out


def main() -> None:
    depth_primary = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not depth_primary.exists():
        depth_primary = INUN / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    depth_sfincs = INUN / "depth_sfincs_queens_ida_m.tif"
    rain = PREC_METRO / "mrms_qpe_metro_storm_total.tif"
    if not rain.exists():
        rain = PREC / "mrms_qpe_ida_precip_storm_total.tif"
    dem = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
    if not dem.exists():
        dem = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"

    scores = score_points_on_depth(
        depth_tif=depth_primary,
        reports_geojson=ASSETS / "observed_311.geojson",
        gauges_geojson=ASSETS / "nwm_ahps_gauges.geojson",
        depth_hit_m=0.03,
    )

    pysheds = _raster_stats(depth_primary)
    sfincs = _raster_stats(depth_sfincs) if depth_sfincs.exists() else None

    overlap = None
    if sfincs is not None:
        with rasterio.open(depth_sfincs) as sf, rasterio.open(depth_primary) as ps:
            s = sf.read(1).astype(np.float64)
            if sf.nodata is not None:
                s = np.where((s == sf.nodata) | (s < -100), np.nan, s)
            p = np.full(s.shape, np.nan, dtype=np.float64)
            reproject(
                source=rasterio.band(ps, 1),
                destination=p,
                src_transform=ps.transform,
                src_crs=ps.crs,
                dst_transform=sf.transform,
                dst_crs=sf.crs,
                resampling=Resampling.bilinear,
                src_nodata=ps.nodata,
                dst_nodata=np.nan,
            )
            both = np.isfinite(s) & np.isfinite(p) & (s >= 0) & (p >= 0)
            mean_s = float(np.nanmean(s[both])) if both.any() else None
            mean_p = float(np.nanmean(p[both])) if both.any() else None
            overlap = {
                "n_cells": int(both.sum()),
                "mean_sfincs_m": mean_s,
                "mean_pysheds_m": mean_p,
                "ratio_mean_sfincs_over_pysheds": (mean_s / mean_p) if mean_s and mean_p else None,
                "max_sfincs_m": float(np.nanmax(s[both])) if both.any() else None,
                "max_pysheds_m": float(np.nanmax(p[both])) if both.any() else None,
            }

    mrms = None
    if rain.exists():
        with rasterio.open(rain) as ds:
            r = ds.read(1).astype(np.float64)
            if ds.nodata is not None:
                r = np.where(r == ds.nodata, np.nan, r)
            pos = r[np.isfinite(r) & (r > 0)]
            mean_mm = float(np.mean(pos)) if pos.size else None
            mrms = {
                "path": str(rain),
                "shape": list(r.shape),
                "bounds": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
                "mean_pos_mm": mean_mm,
                "min_mm": float(pos.min()) if pos.size else None,
                "max_mm": float(pos.max()) if pos.size else None,
                "p10_mm": float(np.percentile(pos, 10)) if pos.size else None,
                "p90_mm": float(np.percentile(pos, 90)) if pos.size else None,
                "cv": float(np.std(pos) / np.mean(pos)) if pos.size else None,
                "forcing_note": (
                    "SFINCS Queens uses spatial MRMS rate field (setup_precip_forcing_from_grid); "
                    "uniform domain-mean forcing removed from primary path."
                ),
            }

    dem_meta = None
    if dem.exists():
        with rasterio.open(dem) as ds:
            lat = (ds.bounds.bottom + ds.bounds.top) / 2.0
            m_lon = 111320.0 * float(np.cos(np.deg2rad(lat)))
            dem_meta = {
                "path": str(dem),
                "shape": list(ds.shape),
                "res_deg": list(ds.res),
                "approx_cell_m": [abs(ds.res[0]) * m_lon, abs(ds.res[1]) * 110540.0],
                "bounds": [ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top],
            }

    rng = np.random.default_rng(42)
    random_hit = None
    land_mask_path = PROCESSED_DIR / "land_mask_metro.tif"
    if not land_mask_path.exists():
        land_mask_path = PROCESSED_DIR / "land_mask_citywide.tif"
    with rasterio.open(depth_primary) as ds:
        d = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            d = np.where(d == ds.nodata, np.nan, d)
        # Sample land polygon cells (incl. dry=NaN), not only finite wet cells.
        if land_mask_path.exists():
            land_arr = np.zeros(d.shape, dtype=np.uint8)
            with rasterio.open(land_mask_path) as lm:
                reproject(
                    source=rasterio.band(lm, 1),
                    destination=land_arr,
                    src_transform=lm.transform,
                    src_crs=lm.crs,
                    dst_transform=ds.transform,
                    dst_crs=ds.crs,
                    resampling=Resampling.nearest,
                )
            land = np.argwhere(land_arr > 0)
        else:
            land = np.argwhere(np.isfinite(d) | True)
        if len(land):
            idx = rng.choice(len(land), size=min(2000, len(land)), replace=False)
            samples = d[land[idx, 0], land[idx, 1]]
            # Treat NaN dry as 0 for hit-rate baseline
            samples = np.where(np.isfinite(samples), samples, 0.0)
            random_hit = float(np.mean(samples >= 0.03))

    sfincs_build = PROJECT_ROOT / "outputs" / "sfincs_queens_ida" / "build_meta.json"
    sfincs_forcing = None
    if sfincs_build.exists():
        sfincs_forcing = json.loads(sfincs_build.read_text())

    report = {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "ida_precip_truth_preference": "mrms_qpe",
        "earth2_role": "scenario_only",
        "primary_depth": {
            "engine": "pysheds_hand_bathtub_v2",
            "extent": PRIMARY_DATA_EXTENT,
            "forcing": "spatial_mrms_qpe_ida",
            "path": str(depth_primary),
            "role": "primary",
        },
        "alternate_depth": {
            "engine": "sfincs_docker_queens",
            "extent": "south_queens",
            "forcing": (sfincs_forcing or {}).get("precip_forcing", "spatial_mrms_grid"),
            "role": "alternate_hydro_track",
            "comparable_to_primary": False,
        },
        "extents": {
            "default_map_extent": DEFAULT_MAP_EXTENT,
            "primary_data_extent": PRIMARY_DATA_EXTENT,
            "data_domain_metro": EXTENTS["metro"]["bounds"],
            "legacy_citywide": EXTENTS["citywide"]["bounds"],
            "sfincs_spike": EXTENTS["south_queens"]["bounds"],
        },
        "validation": scores,
        "random_land_hit_rate_ge_3cm": random_hit,
        "pysheds_metro_mrms": pysheds,
        "sfincs_queens_spatial": sfincs,
        "overlap_queens": overlap,
        "mrms_storm_total": mrms,
        "dem": dem_meta,
        "sfincs_build_meta": sfincs_forcing,
        "honesty": (
            "Primary depth = metro pysheds × spatial MRMS. SFINCS Queens is alternate hydro only. "
            "311 hit rates show spatial concentration, not certified skill / magnitude skill."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "wrote": str(OUT),
                "hit_rate_311": scores["summary"]["hit_rate_311"],
                "hit_rate_gauges": scores["summary"]["hit_rate_gauges"],
                "random_land_hit_rate_ge_3cm": random_hit,
                "ratio_mean_sfincs_over_pysheds": (overlap or {}).get("ratio_mean_sfincs_over_pysheds"),
                "primary_max_m": pysheds.get("max_m"),
                "sfincs_max_m": (sfincs or {}).get("max_m"),
                "default_map_extent": DEFAULT_MAP_EXTENT,
                "dem_approx_cell_m": (dem_meta or {}).get("approx_cell_m"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
