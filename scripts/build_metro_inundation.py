#!/usr/bin/env python3
"""Rebuild primary pysheds HAND/bathtub depth on metro DEM + spatial MRMS.

- Unified HAND params (flood_risk.inundation.hand_bathtub)
- Soft land mask: nodata / transparent alpha outside land (no painted rectangle)
- Primary product labeled metro MRMS → pysheds; writes Decision Desk depth paths

Research only — NOT official NWS / NOT decision-grade.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio import features as rio_features
from rasterio.enums import Resampling
from rasterio.warp import reproject
from shapely.geometry import box, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DEFAULT_EVENT_DURATION_HR,
    EFFECTIVE_DRAINAGE_HOURS,
    ENGINE_ID as DRAINAGE_PROXY_ID,
    capacity_mm_hr,
    drain_density_norm,
    effective_sink_mm,
    load_drain_points,
    load_impervious_fraction,
    param_meta as drainage_param_meta,
)

# Cum-depth timeline: every 3 h from 0–36 so buildup + post-peak recession are visible.
CUM_DEPTH_LEADS_H = list(range(0, 37, 3))
# After peak pooling (~+18h), grow effective drainage hours so excess can recede.
RECESSION_START_H = 18.0
RECESSION_DRAIN_PER_H = 0.35
from flood_risk.inundation.hand_bathtub import (  # noqa: E402
    ENGINE_ID,
    MIN_DEPTH_M,
    compute_terrain_from_dem_path,
    depth_from_rain,
    param_meta,
)
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    LAND_MASK_DATASETS,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402

# HAND/product uses ~30 m working grid derived from 10 m dem_usgs_metro.tif
_DEM_WORK = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif"
_DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
DEM = _DEM_WORK if _DEM_WORK.exists() else _DEM_10M
DEM_10M = _DEM_10M
MRMS_DIR = PROCESSED_DIR / "mrms_qpe_metro"
OUT_DIR = PROCESSED_DIR / "inundation"
ASSETS = FIGURES_DIR / "product_assets"
BOUNDS = EXTENTS[PRIMARY_DATA_EXTENT]["bounds"]
DEPTH_CMAP = "Blues"


def drainage_hours_for_lead(lead_hours: float) -> float:
    """Base flash-window drainage, plus post-peak hours so pooling can recede."""
    extra = max(0.0, float(lead_hours) - RECESSION_START_H) * RECESSION_DRAIN_PER_H
    return float(EFFECTIVE_DRAINAGE_HOURS) + extra


def _land_geometry():
    clip = box(BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"])
    landcover = PROJECT_ROOT / "data" / "raw" / "landcover"
    borough_path = landcover / "nyc_boroughs2.geojson"
    if not borough_path.exists():
        import requests

        borough_path.write_bytes(
            requests.get(
                "https://raw.githubusercontent.com/dwillis/nyc-maps/master/boroughs.geojson",
                timeout=60,
                headers={"User-Agent": "nyc-flood-impact/1.0"},
            ).content
        )
    archive = LAND_MASK_DATASETS["natural_earth_land"]
    ocean_zip = landcover / "ne_10m_ocean.zip"
    if not ocean_zip.exists():
        import requests

        ocean_zip.write_bytes(
            requests.get(
                "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_ocean.zip",
                timeout=120,
            ).content
        )
    if not archive.exists() or not zipfile.is_zipfile(archive):
        raise FileNotFoundError(f"Natural Earth land zip missing: {archive}")
    land_ne = gpd.read_file(f"zip://{archive}").to_crs("EPSG:4326").clip(clip)
    ne_u = unary_union(land_ne.geometry)
    if ocean_zip.exists() and zipfile.is_zipfile(ocean_zip):
        ocean = gpd.read_file(f"zip://{ocean_zip}").to_crs("EPSG:4326").clip(clip)
        if len(ocean):
            ne_u = ne_u.difference(unary_union(ocean.geometry))
    boroughs = gpd.read_file(borough_path).to_crs("EPSG:4326")
    nyc = unary_union(boroughs.geometry)
    # Soft edge: borough shore inside NYC; NE land outside; slight erosion (~40 m)
    land = ne_u.difference(nyc.buffer(0.003)).union(nyc).buffer(-0.00035)
    if ocean_zip.exists() and zipfile.is_zipfile(ocean_zip):
        ocean = gpd.read_file(f"zip://{ocean_zip}").to_crs("EPSG:4326").clip(clip)
        if len(ocean):
            land = land.difference(unary_union(ocean.geometry))
    geo_path = landcover / "land_mask_metro.geojson"
    gpd.GeoDataFrame(
        {"source": ["NYC boroughs + Natural Earth 10m (soft land mask)"]},
        geometry=[land],
        crs="EPSG:4326",
    ).to_file(geo_path, driver="GeoJSON")
    return land


def build_land_mask(height: int, width: int, transform) -> Path:
    land = _land_geometry()
    mask = rio_features.geometry_mask(
        [land], out_shape=(height, width), transform=transform, invert=True
    )
    out = PROCESSED_DIR / "land_mask_metro.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        nodata=0,
        compress="deflate",
    ) as dst:
        dst.write(mask.astype(np.uint8), 1)
        dst.update_tags(extent="metro", soft_edge="true")
    return out


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
        nodata=-9999.0,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)


def _rgba_depth(depth_m: np.ndarray, land: np.ndarray, vmax: float) -> np.ndarray:
    finite = np.isfinite(depth_m) & (depth_m >= MIN_DEPTH_M) & land
    data = np.clip(np.where(np.isfinite(depth_m), depth_m, 0.0) / max(vmax, 1e-6), 0, 1)
    rgba = colormaps[DEPTH_CMAP](data, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(220, 40 + (data * 180).astype(np.uint8)), 0)
    return rgba


def _apply_land(depth: np.ndarray, land: np.ndarray) -> np.ndarray:
    return np.where(land, depth, np.nan)


def _read_rain(path: Path, shape, transform, crs) -> np.ndarray:
    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        if data.shape == shape and src.transform == transform:
            return data
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


def main() -> dict:
    if not DEM.exists():
        raise FileNotFoundError(f"Missing metro DEM: {DEM}")
    rain_total = MRMS_DIR / "mrms_qpe_metro_storm_total.tif"
    if not rain_total.exists():
        raise FileNotFoundError(f"Missing metro MRMS — run regrid_mrms_to_metro.py: {rain_total}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    print("Computing unified HAND/bathtub terrain on metro DEM…")
    terrain = compute_terrain_from_dem_path(DEM)
    with rasterio.open(DEM) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        shape = (dem_ds.height, dem_ds.width)

    print("Building soft metro land mask…")
    mask_path = build_land_mask(shape[0], shape[1], transform)
    with rasterio.open(mask_path) as ms:
        land = ms.read(1) > 0

    _write_tif(OUT_DIR / "hand_metro.tif", terrain["hand"], transform, crs)
    _write_tif(OUT_DIR / "sink_capacity_metro_m.tif", terrain["sink_capacity_m"], transform, crs)

    # Prefer native hourly cumulatives when present; else legacy 6 h interval stacking.
    leads: list[tuple[int, Path]] = []
    for lead in CUM_DEPTH_LEADS_H:
        cum_path = MRMS_DIR / f"mrms_qpe_metro_cum_lead_{lead:02d}h.tif"
        if cum_path.exists():
            leads.append((lead, cum_path))
    use_cum_rasters = bool(leads)
    if not leads:
        for lead in (6, 12, 18, 24):
            path = MRMS_DIR / f"mrms_qpe_metro_lead_{lead:02d}h.tif"
            if path.exists():
                leads.append((lead, path))

    rain = _read_rain(rain_total, shape, transform, crs)

    # Open drainage capacity proxy → effective precip (NOT DEP sewer / NOT SWMM)
    print("Applying open drainage capacity proxy (NLCD + mm/hr sink)…")
    nlcd = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
    if not nlcd.exists():
        raise FileNotFoundError(f"Missing NLCD impervious for drainage proxy: {nlcd}")
    impervious = load_impervious_fraction(shape, transform, crs, nlcd)
    # Prefer real OSM inlets; never use synthetic demo drainage_nodes graph.
    drain_pts, drain_path, drain_status = load_drain_points(
        [
            RAW_DIR / "infrastructure" / "osm_drains_south_queens.geojson",
            ASSETS / "catch_basins.geojson",
            FIGURES_DIR / "ida_v0_assets" / "catch_basins.geojson",
            RAW_DIR / "infrastructure" / "nycdep_catch_basins_south_queens.json",
        ]
    )
    drain_norm = drain_density_norm(shape, transform, drain_pts)
    capacity = capacity_mm_hr(impervious, drain_norm)
    sink_mm, excess_rain, efficiency = effective_sink_mm(
        rain,
        capacity,
        duration_hr=DEFAULT_EVENT_DURATION_HR,
        drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
    )
    drain_dir = PROCESSED_DIR / "drainage_capacity"
    drain_dir.mkdir(parents=True, exist_ok=True)
    _write_tif(drain_dir / "drainage_capacity_mm_hr.tif", capacity, transform, crs)
    _write_tif(drain_dir / "excess_precip_mm.tif", excess_rain, transform, crs)
    _write_tif(drain_dir / "drainage_sink_mm.tif", sink_mm, transform, crs)
    _write_tif(drain_dir / "drainage_efficiency.tif", efficiency, transform, crs)

    # Undrained baseline (diagnostic only — not primary product)
    depth_undrained = _apply_land(
        depth_from_rain(rain, terrain["hand"], terrain["sink_capacity_m"], terrain["dem"]),
        land,
    )
    _write_tif(
        OUT_DIR / "depth_metro_mrms_undrained_ida_storm_total_m.tif",
        depth_undrained,
        transform,
        crs,
    )

    depth = _apply_land(
        depth_from_rain(
            excess_rain, terrain["hand"], terrain["sink_capacity_m"], terrain["dem"]
        ),
        land,
    )
    vmax = float(np.nanpercentile(depth[np.isfinite(depth)], 99)) if np.isfinite(depth).any() else 0.1
    vmax = max(0.05, min(vmax, 3.0))

    # Primary + legacy-compatible filenames for Decision Desk / audit
    primary_stem = "depth_metro_mrms_qpe_ida_storm_total_m"
    legacy_stem = "depth_citywide_mrms_qpe_ida_storm_total_m"
    for stem in (primary_stem, legacy_stem, "depth_mrms_storm_total_m"):
        _write_tif(OUT_DIR / f"{stem}.tif", depth, transform, crs)
        Image.fromarray(_rgba_depth(depth, land, vmax), "RGBA").save(ASSETS / f"{stem}.png", optimize=True)

    cum_frames = []
    cum = np.zeros(shape, dtype=np.float32)
    for lead, path in leads:
        if not path.exists():
            continue
        rain_l = _read_rain(path, shape, transform, crs)
        if use_cum_rasters:
            cum = np.nan_to_num(rain_l, nan=0.0).astype(np.float32)
        else:
            # Legacy path: each file is a 6 h interval → stack into storm cum
            cum = cum + np.nan_to_num(rain_l, nan=0.0)
        drain_h = drainage_hours_for_lead(lead)
        # Duration for surcharge intensity tracks elapsed storm hours (floor at default)
        duration_h = max(float(DEFAULT_EVENT_DURATION_HR), float(lead), 1.0)
        _, excess_cum, efficiency = effective_sink_mm(
            cum,
            capacity,
            duration_hr=duration_h,
            drainage_hours=drain_h,
        )
        d = _apply_land(
            depth_from_rain(
                excess_cum, terrain["hand"], terrain["sink_capacity_m"], terrain["dem"]
            ),
            land,
        )
        for prefix in ("depth_mrms_cum_lead", "depth_metro_mrms_cum_lead"):
            stem = f"{prefix}_{lead:02d}h_m"
            _write_tif(OUT_DIR / f"{stem}.tif", d, transform, crs)
            Image.fromarray(_rgba_depth(d, land, vmax), "RGBA").save(ASSETS / f"{stem}.png", optimize=True)
        cum_frames.append(
            {
                "lead_hours": lead,
                "png": f"depth_metro_mrms_cum_lead_{lead:02d}h_m.png",
                "legacy_png": f"depth_mrms_cum_lead_{lead:02d}h_m.png",
                "tif": str(OUT_DIR / f"depth_metro_mrms_cum_lead_{lead:02d}h_m.tif"),
                "max_m": float(np.nanmax(d)) if np.isfinite(d).any() else None,
                "wet_fraction": float(np.mean(np.isfinite(d) & (d >= MIN_DEPTH_M))),
                "drainage_proxy": DRAINAGE_PROXY_ID,
                "drainage_hours": drain_h,
                "cum_precip_max_mm": float(np.nanmax(cum)) if np.isfinite(cum).any() else None,
                "excess_max_mm": float(np.nanmax(excess_cum)) if np.isfinite(excess_cum).any() else None,
                "efficiency_mean": float(np.nanmean(efficiency[land])) if land.any() else None,
                "evolves_with_timeline": True,
                "phase": (
                    "buildup"
                    if lead < RECESSION_START_H
                    else ("peak" if lead == int(RECESSION_START_H) else "recession")
                ),
            }
        )

    leaflet_bounds = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    storm_total = {
        "png": f"{legacy_stem}.png",
        "tif": str(OUT_DIR / f"{legacy_stem}.tif"),
        "metro_png": f"{primary_stem}.png",
        "metro_tif": str(OUT_DIR / f"{primary_stem}.tif"),
        "max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
        "p95_m": float(np.nanpercentile(depth[np.isfinite(depth)], 95)) if np.isfinite(depth).any() else None,
        "wet_fraction": float(np.mean(np.isfinite(depth) & (depth >= MIN_DEPTH_M))),
        "display_vmax_m": vmax,
        "forcing_max_mm": float(np.nanmax(rain)) if np.isfinite(rain).any() else None,
        "shape": list(shape),
    }

    drain_meta = {
        "engine": DRAINAGE_PROXY_ID,
        "enabled": True,
        "event_duration_hr": DEFAULT_EVENT_DURATION_HR,
        "effective_drainage_hours": EFFECTIVE_DRAINAGE_HOURS,
        "drain_points_n": len(drain_pts),
        "drain_points_status": drain_status,
        "drain_points_path": str(drain_path) if drain_path else None,
        "nlcd": str(nlcd),
        "capacity_mean_mm_hr_land": float(np.mean(capacity[land])) if land.any() else None,
        "excess_mean_mm_land": float(np.nanmean(excess_rain[land])) if land.any() else None,
        "undrained_max_m": (
            float(np.nanmax(depth_undrained)) if np.isfinite(depth_undrained).any() else None
        ),
        "drained_max_m": float(np.nanmax(depth)) if np.isfinite(depth).any() else None,
        **drainage_param_meta(),
    }

    meta = {
        "product": "estimated_research_inundation_depth",
        "primary": True,
        "role": "primary_depth",
        "extent": PRIMARY_DATA_EXTENT,
        "bounds": leaflet_bounds,
        "dem": str(DEM),
        "dem_10m": str(DEM_10M) if DEM_10M.exists() else None,
        "dem_note": (
            "HAND/product on ~30 m working grid derived from USGS 3DEP metro ≤10 m mosaic; "
            "native 10 m DEM retained for SFINCS / nested hydro."
        ),
        "forcing": str(rain_total),
        "forcing_kind": "spatial_mrms_qpe_ida_minus_drainage_capacity_proxy",
        "forcing_raw_mrms": str(rain_total),
        "land_mask": str(mask_path),
        "land_mask_style": "soft_polygon_alpha_nodata_outside_land",
        "drainage_capacity_proxy": drain_meta,
        "storm_total": storm_total,
        "cumulative_frames": cum_frames,
        "cumulative_lead_hours": [fr["lead_hours"] for fr in cum_frames],
        "recession": {
            "start_lead_h": RECESSION_START_H,
            "extra_drainage_hours_per_clock_h": RECESSION_DRAIN_PER_H,
            "note": (
                "After +18h, effective drainage hours grow so HAND excess can recede while "
                "cum precip plateaus — storytelling recession, not a calibrated hydrograph."
            ),
        },
        "forcing_cum_source": "mrms_qpe_metro_cum_lead_*" if use_cum_rasters else "legacy_interval_stack",
        "colorbar": {"cmap": DEPTH_CMAP, "units": "m", "label": "Est. depth (m) — NOT flood warning"},
        "opacity_default": 0.75,
        "not_flood_warning": True,
        "disclaimer": (
            "Primary research depth = unified pysheds HAND/bathtub on metro DEM forced by "
            "spatially varying MRMS QPE Ida after an open drainage capacity proxy "
            "(NLCD impervious + optional drain density + literature mm/hr sink with surcharge). "
            "NOT a DEP sewer model. Soft land mask (alpha/nodata outside land). "
            "NOT official NWS. NOT decision-grade. SFINCS is an alternate hydro track only."
        ),
        **param_meta(),
        "stream_acc_threshold": terrain["stream_acc_threshold"],
    }
    (OUT_DIR / "depth_metro_mrms_qpe_ida_meta.json").write_text(json.dumps(meta, indent=2))
    (OUT_DIR / "depth_citywide_mrms_qpe_ida_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "depth_metro_mrms_qpe_ida_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "depth_citywide_mrms_qpe_ida_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "inundation_meta.json").write_text(json.dumps(meta, indent=2))
    (OUT_DIR / "inundation_meta.json").write_text(json.dumps(meta, indent=2))

    print(
        json.dumps(
            {
                "engine": ENGINE_ID,
                "extent": PRIMARY_DATA_EXTENT,
                "max_m": storm_total["max_m"],
                "wet_fraction": storm_total["wet_fraction"],
                "shape": storm_total["shape"],
                "land_mask": str(mask_path),
            },
            indent=2,
        )
    )
    return meta


if __name__ == "__main__":
    main()
