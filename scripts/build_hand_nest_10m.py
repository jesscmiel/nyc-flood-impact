#!/usr/bin/env python3
"""Phase D — 10 m HAND nest on South Queens Ida corridor vs ~30 m primary + FloodNet.

Clips the native USGS metro ≤10 m DEM to the south_queens extent, runs unified
pysheds HAND/bathtub with the same drainage-proxy excess precip language as the
metro product, and writes a before/after comparison table. Does **not** promote
the nest to product default.

Research only — NOT NWS / NOT decision-grade.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DEFAULT_EVENT_DURATION_HR,
    EFFECTIVE_DRAINAGE_HOURS,
    capacity_mm_hr,
    default_drain_candidate_paths,
    drain_density_norm,
    effective_sink_mm,
    load_drain_points,
    load_impervious_fraction,
)
from flood_risk.inundation.hand_bathtub import (  # noqa: E402
    ENGINE_ID,
    MIN_DEPTH_M,
    compute_terrain_from_dem_path,
    depth_from_rain,
    param_meta,
)
from flood_risk.validate.floodnet import _nearest_wet, _sample_xy  # noqa: E402
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from nyc_flash_flood_case_study.extents import EXTENTS  # noqa: E402

DEM_10M = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif"
BOUNDS = EXTENTS["south_queens"]["bounds"]
OUT = PROCESSED_DIR / "inundation"
ASSETS = FIGURES_DIR / "product_assets"
NEST_DEM = OUT / "dem_south_queens_10m.tif"
NEST_DEPTH = OUT / "depth_hand_nest_10m_south_queens_ida_m.tif"
PRIMARY_30 = OUT / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
EXCESS = PROCESSED_DIR / "drainage_capacity" / "excess_precip_mm.tif"
MRMS = PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif"
NLCD = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
FLOODNET = PROCESSED_DIR / "floodnet" / "floodnet_ida_events.geojson"


def _clip_dem() -> Path:
    if not DEM_10M.exists():
        raise FileNotFoundError(
            f"Missing 10 m metro DEM ({DEM_10M}). Run scripts/fetch_metro_dem.py."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(DEM_10M) as src:
        window = from_bounds(
            BOUNDS["xmin"],
            BOUNDS["ymin"],
            BOUNDS["xmax"],
            BOUNDS["ymax"],
            transform=src.transform,
        )
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window).astype(np.float32)
        transform = src.window_transform(window)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        profile = src.profile.copy()
        profile.update(
            height=data.shape[0],
            width=data.shape[1],
            transform=transform,
            dtype="float32",
            nodata=-9999.0,
            compress="deflate",
            tiled=True,
        )
        with rasterio.open(NEST_DEM, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)
    return NEST_DEM


def _warp_to(path: Path, shape: tuple[int, int], transform, crs) -> np.ndarray:
    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        src_data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            src_data = np.where(src_data == src.nodata, np.nan, src_data)
        reproject(
            source=src_data,
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


def _rgba(depth: np.ndarray, vmax: float) -> np.ndarray:
    finite = np.isfinite(depth) & (depth >= MIN_DEPTH_M)
    norm = np.clip(np.nan_to_num(depth, nan=0.0) / max(vmax, 1e-6), 0, 1)
    rgba = colormaps["Blues"](norm, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(230, 50 + (norm * 180).astype(np.uint8)), 0)
    return rgba


def _floodnet_rows(depth_tif: Path) -> list[dict]:
    if not FLOODNET.exists():
        return []
    events = json.loads(FLOODNET.read_text())
    rows: list[dict] = []
    with rasterio.open(depth_tif) as ds:
        for feat in events.get("features") or []:
            props = feat.get("properties") or {}
            lon, lat = feat["geometry"]["coordinates"][:2]
            model = _sample_xy(ds, float(lon), float(lat))
            nearest = _nearest_wet(ds, float(lon), float(lat), search_m=250.0)
            obs = props.get("peak_depth_m")
            if obs is None:
                obs = props.get("max_depth_m")
            rows.append(
                {
                    "sensor_id": props.get("sensor_id") or props.get("deployment_id"),
                    "borough": props.get("borough"),
                    "lon": lon,
                    "lat": lat,
                    "obs_peak_m": obs,
                    "model_at_point_m": model,
                    "nearest_wet_m": nearest.get("depth_m"),
                    "nearest_wet_dist_m": nearest.get("dist_m"),
                    "bias_at_point_m": (
                        float(model) - float(obs)
                        if obs is not None and np.isfinite(model)
                        else None
                    ),
                }
            )
    return rows


def _skill(rows: list[dict]) -> dict:
    obs = np.array([r["obs_peak_m"] for r in rows if r["obs_peak_m"] is not None], dtype=float)
    mod = np.array(
        [r["model_at_point_m"] for r in rows if r["obs_peak_m"] is not None], dtype=float
    )
    if obs.size == 0:
        return {"n": 0}
    bias = mod - obs
    return {
        "n": int(obs.size),
        "obs_mean_m": float(np.mean(obs)),
        "obs_max_m": float(np.max(obs)),
        "model_mean_m": float(np.mean(mod)),
        "model_max_m": float(np.max(mod)),
        "peak_bias_m": float(np.mean(bias)),
        "peak_rmse_m": float(np.sqrt(np.mean(bias**2))),
        "n_wet_at_point": int(np.sum(mod >= MIN_DEPTH_M)),
    }


def main() -> dict:
    dem_path = _clip_dem()
    print(f"Clipped 10 m DEM → {dem_path}")
    print("Computing HAND terrain on nest…")
    terrain = compute_terrain_from_dem_path(dem_path)
    with rasterio.open(dem_path) as dem_ds:
        transform = dem_ds.transform
        crs = dem_ds.crs
        shape = (dem_ds.height, dem_ds.width)

    # Prefer prebuilt excess precip; else rebuild sink on nest grid from MRMS.
    if EXCESS.exists():
        rain_eff = _warp_to(EXCESS, shape, transform, crs)
        forcing_kind = "warped_metro_excess_precip_after_drainage_proxy"
    else:
        if not MRMS.exists() or not NLCD.exists():
            raise FileNotFoundError("Need excess_precip_mm.tif or MRMS+NLCD for nest forcing")
        rain = _warp_to(MRMS, shape, transform, crs)
        impervious = load_impervious_fraction(shape, transform, crs, NLCD)
        pts, _, _ = load_drain_points(
            default_drain_candidate_paths(RAW_DIR / "infrastructure", ASSETS, RAW_DIR)
        )
        cap = capacity_mm_hr(impervious, drain_density_norm(shape, transform, pts))
        _, rain_eff, _ = effective_sink_mm(
            rain,
            cap,
            duration_hr=DEFAULT_EVENT_DURATION_HR,
            drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
        )
        forcing_kind = "nest_recomputed_excess_precip_after_drainage_proxy"

    depth = depth_from_rain(
        rain_eff, terrain["hand"], terrain["sink_capacity_m"], terrain["dem"]
    )
    with rasterio.open(
        NEST_DEPTH,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(np.where(np.isfinite(depth), depth, -9999.0).astype(np.float32), 1)

    finite = depth[np.isfinite(depth)]
    vmax = float(np.nanpercentile(finite, 99)) if finite.size else 0.1
    vmax = max(0.05, min(vmax, 3.0))
    png_name = "depth_hand_nest_10m_south_queens_ida_m.png"
    Image.fromarray(_rgba(depth, vmax), "RGBA").save(ASSETS / png_name, optimize=True)

    # Persist HAND nest raster for inspection
    hand_path = OUT / "hand_south_queens_10m.tif"
    with rasterio.open(
        hand_path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        hand = terrain["hand"]
        dst.write(np.where(np.isfinite(hand), hand, -9999.0).astype(np.float32), 1)

    nest_rows = _floodnet_rows(NEST_DEPTH)
    primary_rows = _floodnet_rows(PRIMARY_30) if PRIMARY_30.exists() else []
    nest_skill = _skill(nest_rows)
    primary_skill = _skill(primary_rows)

    # Pairwise table
    by_id_p = {r["sensor_id"]: r for r in primary_rows}
    table = []
    for r in nest_rows:
        p = by_id_p.get(r["sensor_id"], {})
        table.append(
            {
                "sensor_id": r["sensor_id"],
                "borough": r["borough"],
                "obs_peak_m": r["obs_peak_m"],
                "hand_30m_at_point_m": p.get("model_at_point_m"),
                "hand_10m_at_point_m": r["model_at_point_m"],
                "hand_30m_nearest_wet_m": p.get("nearest_wet_m"),
                "hand_10m_nearest_wet_m": r["nearest_wet_m"],
                "hand_10m_nearest_dist_m": r["nearest_wet_dist_m"],
            }
        )

    promote = False
    promote_reason = (
        "Nest remains cm-scale vs FloodNet street peaks; do not auto-promote to product "
        "default or peer depth toggle."
    )
    if (
        nest_skill.get("n", 0) > 0
        and primary_skill.get("n", 0) > 0
        and nest_skill.get("peak_rmse_m") is not None
        and primary_skill.get("peak_rmse_m") is not None
        and nest_skill["peak_rmse_m"] < primary_skill["peak_rmse_m"] * 0.7
        and nest_skill.get("model_max_m", 0) >= 0.15
    ):
        promote = False  # still require human review; flag as candidate only
        promote_reason = (
            "Nest RMSE improved vs 30 m but still not street-truth — Advanced-only "
            "candidate at most; product default unchanged."
        )

    report = {
        "phase": "D",
        "product": "hand_nest_10m_south_queens",
        "extent": "south_queens",
        "bounds": BOUNDS,
        "engine": ENGINE_ID,
        "hand_params": param_meta(),
        "dem_10m": str(DEM_10M),
        "nest_dem": str(NEST_DEM),
        "nest_depth_tif": str(NEST_DEPTH),
        "nest_depth_png": png_name,
        "hand_tif": str(hand_path),
        "shape": list(shape),
        "res_approx_deg": [abs(transform.a), abs(transform.e)],
        "forcing_kind": forcing_kind,
        "stats": {
            "max_m": float(np.nanmax(depth)) if finite.size else None,
            "p95_m": float(np.nanpercentile(finite, 95)) if finite.size else None,
            "wet_fraction": float(np.mean(np.isfinite(depth) & (depth >= MIN_DEPTH_M))),
        },
        "vs_floodnet": {
            "hand_10m_nest": nest_skill,
            "hand_30m_primary": primary_skill,
            "sensor_table": table,
        },
        "product_default_unchanged": True,
        "promote_to_advanced": promote,
        "promote_reason": promote_reason,
        "honesty": (
            "10 m HAND nest is a resolution experiment on the same bathtub physics — "
            "still cm-scale screening, not street-truth Ida. Primary metro ~30 m HAND "
            "remains the only default depth."
        ),
        "official_nws": False,
        "decision_grade": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUT / "hand_nest_10m_comparison.json").write_text(json.dumps(report, indent=2))
    (ASSETS / "hand_nest_10m_comparison.json").write_text(json.dumps(report, indent=2))
    (OUTPUTS_DIR / "hand_nest_10m_comparison.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "shape": list(shape),
                "nest_max_m": report["stats"]["max_m"],
                "floodnet_10m_rmse": nest_skill.get("peak_rmse_m"),
                "floodnet_30m_rmse": primary_skill.get("peak_rmse_m"),
                "promote": promote,
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    main()
