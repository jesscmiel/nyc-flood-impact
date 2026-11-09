#!/usr/bin/env python3
"""Rebuild citywide precip/pluvial assets with correct georeferencing.

- Earth2: clip more ~0.25° cells for NYC metro; render with nearest-neighbor
  onto a display grid that matches the native cell footprint (no stretch to a
  larger empty bbox).
- MRMS / pluvial / NLCD: regenerate for the same citywide extent.
- Manifest records per-layer geographic bounds for Leaflet (do not stretch).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT, RAW_DIR
from nyc_flash_flood_case_study.extents import EXTENTS
from nyc_flash_flood_case_study.forecast import normalize_earth2_forecast
from nyc_flash_flood_case_study.pluvial import build_pluvial_screening

ASSETS = FIGURES_DIR / "product_assets"
E2_DIR = PROCESSED_DIR / "earth2_precip"
MRMS_DIR = PROCESSED_DIR / "mrms_qpe"
EXTENT_ID = "citywide"
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]
DISPLAY_SHAPE = (360, 480)  # H, W over citywide bbox


def _rgba(values: np.ndarray, cmap_name: str, vmax: float, opacity: int = 200) -> np.ndarray:
    finite = np.isfinite(values)
    data = np.where(finite, values, 0.0).astype(np.float32)
    vmax = max(float(vmax), 1e-6)
    normalized = np.clip(data / vmax, 0.0, 1.0)
    rgba = colormaps[cmap_name](normalized, bytes=True)
    rgba[..., 3] = np.where(finite & (data > 0.02), np.minimum(opacity, 55 + (normalized * 180).astype(np.uint8)), 0)
    return rgba


def _write_png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)


def _write_tif(path: Path, data: np.ndarray, transform) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)


def _native_cell_bounds(lat: np.ndarray, lon: np.ndarray) -> dict:
    """Geographic footprint of Earth2 cell edges (centers ± half spacing)."""
    dlat = float(np.median(np.abs(np.diff(lat)))) if lat.size > 1 else 0.25
    dlon = float(np.median(np.abs(np.diff(lon)))) if lon.size > 1 else 0.25
    return {
        "xmin": float(lon.min()) - dlon / 2,
        "xmax": float(lon.max()) + dlon / 2,
        "ymin": float(lat.min()) - dlat / 2,
        "ymax": float(lat.max()) + dlat / 2,
        "dlat": dlat,
        "dlon": dlon,
    }


def _render_nearest_to_extent(
    field: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    extent_bounds: dict,
    shape: tuple[int, int] = DISPLAY_SHAPE,
) -> tuple[np.ndarray, object, dict]:
    """Nearest-neighbor paint of native cells into an extent grid; NaN outside cells."""
    if lat[0] < lat[-1]:
        field = field[::-1, :]
        lat = lat[::-1]
    cell = _native_cell_bounds(lat, lon)
    # Source transform covers only the native footprint.
    src_transform = from_bounds(
        cell["xmin"], cell["ymin"], cell["xmax"], cell["ymax"], field.shape[1], field.shape[0]
    )
    dst = np.full(shape, np.nan, dtype=np.float32)
    dst_transform = from_bounds(
        extent_bounds["xmin"],
        extent_bounds["ymin"],
        extent_bounds["xmax"],
        extent_bounds["ymax"],
        shape[1],
        shape[0],
    )
    reproject(
        source=field.astype(np.float32),
        destination=dst,
        src_transform=src_transform,
        src_crs="EPSG:4326",
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        resampling=Resampling.nearest,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    leaflet_bounds = [
        [extent_bounds["ymin"], extent_bounds["xmin"]],
        [extent_bounds["ymax"], extent_bounds["xmax"]],
    ]
    meta = {
        "leaflet_bounds": leaflet_bounds,
        "native_cell_bounds": cell,
        "resampling": "nearest",
        "note": "Nearest-neighbor display of native ~0.25° cells; transparent outside footprint. Not downscaling.",
    }
    return dst, dst_transform, meta


def clip_forecast_citywide() -> Path:
    """Normalize global Ida forecast into a citywide clipped NetCDF."""
    # Temporarily write using normalize with patched STUDY_AREA via local copy logic.
    global_nc = PROJECT_ROOT / "data" / "forecasts" / "earth2_precip_ida_20210901T12.nc"
    if not global_nc.exists():
        sibling = Path(
            "/home/jesscmiel/projects/earth2studio/projects/nyc_flash_flood_case_study/data/forecasts/earth2_precip_ida_20210901T12.nc"
        )
        if sibling.exists():
            shutil.copy2(sibling, global_nc)
    out = PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_citywide.nc"

    # Inline clip using citywide bounds (avoid mutating module STUDY_AREA permanently).
    from nyc_flash_flood_case_study import config as config_mod
    from nyc_flash_flood_case_study import forecast as forecast_mod

    # Both modules hold a reference to STUDY_AREA — mutate in place AND rebind.
    original_bounds = dict(config_mod.STUDY_AREA["bounds"])
    original_name = config_mod.STUDY_AREA["name"]
    city = {
        "name": "NYC citywide (approx.)",
        "bounds": dict(BOUNDS),
        "crs": "EPSG:4326",
    }
    config_mod.STUDY_AREA.clear()
    config_mod.STUDY_AREA.update(city)
    forecast_mod.STUDY_AREA = config_mod.STUDY_AREA
    try:
        normalize_earth2_forecast(global_nc, out)
    finally:
        config_mod.STUDY_AREA.clear()
        config_mod.STUDY_AREA.update(
            {"name": original_name, "bounds": original_bounds, "crs": "EPSG:4326"}
        )
        forecast_mod.STUDY_AREA = config_mod.STUDY_AREA
    return out


def export_earth2(clipped: Path) -> dict:
    E2_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    with xr.open_dataset(clipped) as ds:
        precip = ds["precipitation_mm"]
        if "ensemble" in precip.dims:
            precip = precip.isel(ensemble=0)
        lat = precip.lat.values.astype(np.float64)
        lon = precip.lon.values.astype(np.float64)
        leads = [float(v) for v in precip.lead_time_hours.values]
        valids = [str(np.datetime64(v, "m")) for v in precip.valid_time.values]
        vmax = max(float(np.nanmax(precip.values)), 1.0)
        frames = []
        total = None
        geo_meta = None
        for i, (lead, valid) in enumerate(zip(leads, valids)):
            field = precip.isel(lead_time_hours=i).values.astype(np.float32)
            display, transform, geo_meta = _render_nearest_to_extent(field, lat, lon, BOUNDS)
            total = display if total is None else np.nansum(np.stack([total, np.nan_to_num(display)]), axis=0)
            total = np.where(np.isfinite(display) | np.isfinite(total if total is not None else display), total, np.nan)
            stem = f"precip_lead_{int(lead):02d}h"
            _write_tif(E2_DIR / f"{stem}.tif", display, transform)
            _write_png(ASSETS / f"{stem}.png", _rgba(display, "Blues", vmax=max(vmax, 5.0)))
            frames.append(
                {
                    "index": i,
                    "lead_hours": int(lead),
                    "valid_time": valid.replace("T", "T")[:16],
                    "png": f"{stem}.png",
                    "tif": str(E2_DIR / f"{stem}.tif"),
                    "mean_mm": float(np.nanmean(field)),
                    "max_mm": float(np.nanmax(field)),
                    "native_shape": list(field.shape),
                }
            )
        # Storm total from native sum then render
        native_total = precip.sum("lead_time_hours").values.astype(np.float32)
        display_total, transform, geo_meta = _render_nearest_to_extent(native_total, lat, lon, BOUNDS)
        _write_tif(E2_DIR / "precip_storm_total.tif", display_total, transform)
        _write_png(ASSETS / "precip_storm_total.png", _rgba(display_total, "BuPu", vmax=max(float(np.nanmax(native_total)), 10.0)))
        cell = geo_meta["native_cell_bounds"]
        return {
            "init_time": str(ds.attrs.get("forecast_initialization_time", "")),
            "forecast_model": str(ds.attrs.get("forecast_model", "FourCastNet + PrecipitationAFNO")),
            "frames": frames,
            "storm_total_png": "precip_storm_total.png",
            "storm_total_tif": str(E2_DIR / "precip_storm_total.tif"),
            "storm_total_max_mm": float(np.nanmax(native_total)),
            "storm_total_mean_mm": float(np.nanmean(native_total)),
            "interval_hours": float(ds.attrs.get("interval_hours", 6)),
            "bounds": geo_meta["leaflet_bounds"],
            "data_bounds": geo_meta["leaflet_bounds"],
            "native_cell_bounds": cell,
            "native_grid": {"n_lat": int(lat.size), "n_lon": int(lon.size), "lat": lat.tolist(), "lon": lon.tolist()},
            "display_note": (
                "Earth2 precip shown as nearest-neighbor ~0.25° cells over the NYC metro extent. "
                "Not street-scale truth; bilinear UI toggle only changes CSS image-rendering."
            ),
            "resampling": "nearest",
            "extent_id": EXTENT_ID,
        }


def warp_existing_mrms_to_citywide() -> dict | None:
    """Reproject existing South Queens MRMS frames onto citywide grid if present."""
    old = ASSETS / "mrms_qpe_qa.json"
    if not (MRMS_DIR / "mrms_qpe_storm_total.tif").exists():
        return None
    frames_out = []
    with rasterio.open(MRMS_DIR / "mrms_qpe_storm_total.tif") as src:
        # Prefer rebuilding from lead tifs if available
        pass
    # Use lead tifs from processed dir
    lead_tifs = sorted(MRMS_DIR.glob("mrms_qpe_lead_*h.tif"))
    if not lead_tifs:
        return None
    dst_transform = from_bounds(BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"], DISPLAY_SHAPE[1], DISPLAY_SHAPE[0])
    leaflet = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    storm = np.zeros(DISPLAY_SHAPE, dtype=np.float32)
    vmax = 1.0
    meta_frames = []
    for tif in lead_tifs:
        dst = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        with rasterio.open(tif) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs or "EPSG:4326",
                dst_transform=dst_transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
                src_nodata=src.nodata,
                dst_nodata=np.nan,
            )
        lead = int("".join(ch for ch in tif.stem if ch.isdigit()) or 0)
        # digits may be 0612 etc — parse from name precip style mrms_qpe_lead_12h
        parts = tif.stem.split("_")
        lead = int(parts[-1].replace("h", ""))
        vmax = max(vmax, float(np.nanmax(dst)) if np.isfinite(dst).any() else 0)
        storm = np.nansum(np.stack([storm, np.nan_to_num(dst)]), axis=0)
        out_tif = MRMS_DIR / f"mrms_qpe_lead_{lead:02d}h_citywide.tif"
        _write_tif(out_tif, dst, dst_transform)
        png = f"mrms_qpe_lead_{lead:02d}h.png"
        _write_png(ASSETS / png, _rgba(dst, "YlGnBu", vmax=max(float(np.nanmax(dst)), 5.0)))
        meta_frames.append(
            {
                "lead_hours": lead,
                "png": png,
                "tif": str(out_tif),
                "max_mm": float(np.nanmax(dst)) if np.isfinite(dst).any() else 0.0,
                "mean_mm": float(np.nanmean(dst)) if np.isfinite(dst).any() else 0.0,
            }
        )
    # Re-render with shared vmax
    for fr in meta_frames:
        with rasterio.open(fr["tif"]) as src:
            dst = src.read(1, masked=True).filled(np.nan)
        _write_png(ASSETS / fr["png"], _rgba(dst, "YlGnBu", vmax=max(vmax, 5.0)))
    _write_tif(MRMS_DIR / "mrms_qpe_storm_total.tif", storm, dst_transform)
    _write_png(ASSETS / "mrms_qpe_storm_total.png", _rgba(storm, "YlGnBu", vmax=max(float(np.nanmax(storm)), 10.0)))
    return {
        "product": "MultiSensor_QPE_01H_Pass1_00.00",
        "product_note": "MRMS QPE reprojected/padded to citywide display grid. Outside original South Queens pull may be empty.",
        "frames": meta_frames,
        "storm_total_png": "mrms_qpe_storm_total.png",
        "storm_total_max_mm": float(np.nanmax(storm)),
        "storm_total_mean_mm": float(np.nanmean(storm)),
        "bounds": leaflet,
        "data_bounds": leaflet,
        "shared_display_vmax_mm": float(vmax),
        "extent_id": EXTENT_ID,
    }


def main() -> None:
    print("Clipping Earth2 forecast to citywide…")
    clipped = clip_forecast_citywide()
    with xr.open_dataset(clipped) as ds:
        print(f"  clipped grid lat={list(ds.lat.values)} lon={list(ds.lon.values)}")
    precip = export_earth2(clipped)
    print(f"  Earth2 frames={len(precip['frames'])} native={precip['native_grid']}")

    print("Building citywide pluvial (NLCD + terrain)…")
    nlcd = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
    if not nlcd.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "fetch_nlcd_impervious", PROJECT_ROOT / "scripts" / "fetch_nlcd_impervious.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        mod.fetch_nlcd_impervious("citywide", nlcd)
    # Prefer citywide NLCD path in finder by ensuring file exists under expected name
    pluvial = build_pluvial_screening(extent_id=EXTENT_ID, assets_dir=ASSETS)
    print(f"  pluvial mean={pluvial['mean']:.2f} kind={pluvial['impervious_kind']}")

    print("Warping MRMS to citywide display…")
    mrms = warp_existing_mrms_to_citywide()

    # Update / write product-oriented manifest fragment
    manifest_path = ASSETS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["event"] = "Hurricane Ida remnants over NYC"
    manifest["study_area"] = "NYC citywide (approx.)"
    manifest["precip"] = precip
    if mrms:
        # Keep old diff frames if any; clear if bounds mismatch
        old = manifest.get("mrms_qpe") or {}
        mrms["diff_frames"] = []  # rebuild diffs optionally later
        mrms["init_time"] = precip.get("init_time")
        # Preserve valid times from precip frames where possible
        for i, fr in enumerate(mrms["frames"]):
            if i < len(precip["frames"]):
                fr["valid_time"] = precip["frames"][i]["valid_time"]
        manifest["mrms_qpe"] = mrms
    manifest["layer_bounds"] = {
        "precip": precip["bounds"],
        "mrms": (mrms or {}).get("bounds", precip["bounds"]),
        "pluvial": pluvial.get("bounds"),
        "map_extent_default": EXTENT_ID,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    (ASSETS / "layer_bounds.json").write_text(json.dumps(manifest["layer_bounds"], indent=2))
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
