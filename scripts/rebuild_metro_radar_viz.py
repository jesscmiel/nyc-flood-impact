#!/usr/bin/env python3
"""Rebuild MRMS Ida precip + susceptibility PNGs on the metro domain.

Fixes the hard citywide rectangle inset over the continuous metro map frame:
- Source = data/processed/mrms_qpe_metro (spatial MRMS on DEM grid)
- Soft edge feather + soft land mask (transparent water / domain rim)
- 1h temporal blends between native 6/12/18/24h leads
- Updates product manifests so Leaflet bounds match metro depth

Research viz only — NOT NEXRAD tiles / NOT NWS.
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
from rasterio.transform import from_bounds
from rasterio.warp import reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR  # noqa: E402
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402
from build_multifactor_susceptibility import FORMULA, combine_frame  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
E2_DIR = PROCESSED_DIR / "earth2_precip"
SUSC_DIR = PROCESSED_DIR / "susceptibility"
MRMS_DIR = PROCESSED_DIR / "mrms_qpe_metro"
LAND_MASK = PROCESSED_DIR / "land_mask_metro.tif"

EXTENT_ID = PRIMARY_DATA_EXTENT  # metro
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]
# Display grid for Leaflet overlays (lighter than full 30 m product grid)
DISPLAY_SHAPE = (720, 800)  # (H, W)
PRECIP_CMAP = "turbo"
SUSC_CMAP = "YlOrRd"
FEATHER_PX = 36
PREFIX = "mrms_qpe_ida_"
NATIVE_LEADS = (6, 12, 18, 24)
INIT_TIME = "2021-09-01T12:00"


def _leaflet_bounds() -> list:
    return [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]


def _display_transform():
    return from_bounds(
        BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"],
        DISPLAY_SHAPE[1], DISPLAY_SHAPE[0],
    )


def _warp_to_display(src_path: Path, dst: np.ndarray, transform) -> np.ndarray:
    with rasterio.open(src_path) as src:
        data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        reproject(
            source=data,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    return dst


def _soft_edge_fade(shape: tuple[int, int], feather: int = FEATHER_PX) -> np.ndarray:
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.minimum.reduce([yy, xx, h - 1 - yy, w - 1 - xx]).astype(np.float32)
    return np.clip(dist / max(feather, 1), 0.0, 1.0)


def _load_land_fade(transform) -> np.ndarray:
    land = np.zeros(DISPLAY_SHAPE, dtype=np.float32)
    if LAND_MASK.exists():
        with rasterio.open(LAND_MASK) as src:
            data = src.read(1).astype(np.float32)
            if src.nodata is not None:
                data = np.where(data == src.nodata, 0.0, data)
            reproject(
                source=data,
                destination=land,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
                src_nodata=src.nodata,
                dst_nodata=0.0,
            )
        land = np.clip(land, 0, 1)
    else:
        land = np.ones(DISPLAY_SHAPE, dtype=np.float32)
    # Soften land/water transition a bit
    land = np.clip(land * 1.15, 0, 1)
    return land * _soft_edge_fade(DISPLAY_SHAPE)


def _rgba_precip(values: np.ndarray, vmax: float, fade: np.ndarray, opacity: int = 220) -> np.ndarray:
    finite = np.isfinite(values) & (values > 0.08) & (fade > 0.02)
    data = np.where(np.isfinite(values), values, 0.0).astype(np.float32)
    vmax = max(float(vmax), 1e-6)
    normalized = np.clip(data / vmax, 0.0, 1.0)
    rgba = colormaps[PRECIP_CMAP](normalized, bytes=True)
    base = np.where(finite, np.minimum(opacity, 45 + (normalized * 200).astype(np.uint8)), 0).astype(np.float32)
    rgba[..., 3] = np.clip(base * fade, 0, 255).astype(np.uint8)
    return rgba


def _rgba_susc(values: np.ndarray, fade: np.ndarray, opacity: int = 210) -> np.ndarray:
    # Lower threshold + stronger alpha so screening is glanceable when toggled on
    finite = np.isfinite(values) & (values > 0.02) & (fade > 0.02)
    data = np.clip(np.where(np.isfinite(values), values, 0.0), 0, 1).astype(np.float32)
    rgba = colormaps[SUSC_CMAP](data, bytes=True)
    base = np.where(finite, np.minimum(opacity, 55 + (data * 200).astype(np.uint8)), 0).astype(np.float32)
    rgba[..., 3] = np.clip(base * fade, 0, 255).astype(np.uint8)
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


def _valid_time(lead_hours: float) -> str:
    # init 2021-09-01T12:00 UTC + lead
    total = 12 + int(round(lead_hours))
    day = 1 + total // 24
    hour = total % 24
    return f"2021-09-{day:02d}T{hour:02d}:00"


def _blend_stack(native: list[dict], step_hours: float = 1.0) -> list[dict]:
    if len(native) < 2:
        return native
    out: list[dict] = []
    for i, left in enumerate(native):
        out.append(left)
        if i == len(native) - 1:
            break
        right = native[i + 1]
        dt = right["lead_hours"] - left["lead_hours"]
        if dt <= step_hours:
            continue
        n_steps = int(round(dt / step_hours))
        for k in range(1, n_steps):
            alpha = k / n_steps
            mid_lead = left["lead_hours"] + dt * alpha
            blended = (1 - alpha) * left["field"] + alpha * right["field"]
            out.append(
                {
                    "lead_hours": float(mid_lead),
                    "valid_time": _valid_time(mid_lead),
                    "field": blended.astype(np.float32),
                    "native": False,
                    "temporal_blend": True,
                    "blend_of": [left["lead_hours"], right["lead_hours"]],
                    "blend_alpha": alpha,
                }
            )
    out.sort(key=lambda f: f["lead_hours"])
    return out


def _warp_factor(path: Path, transform) -> np.ndarray:
    out = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
    if not path.exists():
        return np.zeros(DISPLAY_SHAPE, dtype=np.float32)
    return _warp_to_display(path, out, transform)


def main() -> dict:
    ASSETS.mkdir(parents=True, exist_ok=True)
    E2_DIR.mkdir(parents=True, exist_ok=True)
    SUSC_DIR.mkdir(parents=True, exist_ok=True)

    transform = _display_transform()
    fade = _load_land_fade(transform)

    factor_dir = PROCESSED_DIR / "susceptibility_factors"
    landscape = _warp_factor(factor_dir / "factor_landscape.tif", transform)
    infra = _warp_factor(factor_dir / "factor_infra.tif", transform)
    # Prefer metro impervious when available
    imp_metro = PROCESSED_DIR / "drainage_capacity" / "impervious_fraction_metro.tif"
    if imp_metro.exists():
        imp = _warp_factor(imp_metro, transform)
        terrain = _warp_factor(factor_dir / "factor_terrain.tif", transform)
        landscape = np.clip(0.55 * np.nan_to_num(terrain, nan=0.0) + 0.45 * np.nan_to_num(imp, nan=0.0), 0, 1)

    native_fields: list[dict] = []
    for lead in NATIVE_LEADS:
        path = MRMS_DIR / f"mrms_qpe_metro_lead_{lead:02d}h.tif"
        if not path.exists():
            raise FileNotFoundError(f"Missing metro MRMS lead: {path}")
        field = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        _warp_to_display(path, field, transform)
        native_fields.append(
            {
                "lead_hours": float(lead),
                "valid_time": _valid_time(lead),
                "field": field,
                "native": True,
                "temporal_blend": False,
            }
        )

    dense = _blend_stack(native_fields, step_hours=1.0)
    vmax = max(
        (float(np.nanmax(f["field"])) for f in dense if np.isfinite(f["field"]).any()),
        default=1.0,
    )

    precip_frames, susc_frames = [], []
    fields_for_rerender = []
    for i, fr in enumerate(dense):
        display = fr["field"].astype(np.float32)
        fields_for_rerender.append(display)
        lead = fr["lead_hours"]
        if fr["temporal_blend"]:
            stem = f"{PREFIX}precip_lead_{int(round(lead)):02d}h_blend"
        else:
            stem = f"{PREFIX}precip_lead_{int(round(lead)):02d}h"
        _write_tif(E2_DIR / f"{stem}.tif", display, transform)
        _write_png(ASSETS / f"{stem}.png", _rgba_precip(display, vmax=max(vmax, 5.0), fade=fade))

        pnorm = np.clip(np.nan_to_num(display, nan=0.0) / max(vmax, 1e-6), 0, 1)
        susc = combine_frame(landscape, infra, pnorm)
        susc = np.where(fade > 0.05, susc, np.nan)
        susc_stem = stem.replace("precip_", "susc_")
        _write_tif(SUSC_DIR / f"{susc_stem}.tif", susc, transform)
        _write_png(ASSETS / f"{susc_stem}.png", _rgba_susc(susc, fade=fade))

        precip_frames.append(
            {
                "index": i,
                "lead_hours": float(lead),
                "valid_time": fr["valid_time"],
                "png": f"{stem}.png",
                "tif": str(E2_DIR / f"{stem}.tif"),
                "mean_mm": float(np.nanmean(display)),
                "max_mm": float(np.nanmax(display)) if np.isfinite(display).any() else None,
                "native": fr["native"],
                "temporal_blend": fr["temporal_blend"],
                "blend_of": fr.get("blend_of"),
                "resolution_note": "~1 km MRMS Multi-Sensor QPE on metro DEM grid — soft land+edge alpha",
            }
        )
        susc_frames.append(
            {
                "index": i,
                "lead_hours": float(lead),
                "valid_time": fr["valid_time"],
                "png": f"{susc_stem}.png",
                "tif": str(SUSC_DIR / f"{susc_stem}.tif"),
                "mean": float(np.nanmean(susc)) if np.isfinite(susc).any() else None,
                "formula": FORMULA,
            }
        )

    # Final vmax pass
    for fr, field in zip(precip_frames, fields_for_rerender):
        _write_png(ASSETS / fr["png"], _rgba_precip(field, vmax=max(vmax, 5.0), fade=fade))

    total_path = MRMS_DIR / "mrms_qpe_metro_storm_total.tif"
    total = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
    _warp_to_display(total_path, total, transform)
    total_png = f"{PREFIX}precip_storm_total.png"
    _write_tif(E2_DIR / f"{PREFIX}precip_storm_total.tif", total, transform)
    _write_png(ASSETS / total_png, _rgba_precip(total, vmax=max(float(np.nanmax(total)), 10.0), fade=fade))

    leaflet = _leaflet_bounds()
    time_window = {
        "init_time_utc": INIT_TIME,
        "first_valid_time_utc": precip_frames[0]["valid_time"] if precip_frames else None,
        "last_valid_time_utc": precip_frames[-1]["valid_time"] if precip_frames else None,
        "lead_hours_min": precip_frames[0]["lead_hours"] if precip_frames else None,
        "lead_hours_max": precip_frames[-1]["lead_hours"] if precip_frames else None,
        "native_leads_h": list(NATIVE_LEADS),
        "loop_step_h": 1.0,
        "n_frames": len(precip_frames),
        "note": (
            "Ida MRMS awareness loop covers +6h…+24h from 2021-09-01T12:00 UTC "
            "(valid 2021-09-01T18:00 → 2021-09-02T12:00). Depth cum frames exist at 6/12/18/24h only."
        ),
        "longer_modeling_recommendation": (
            "Extend earlier (0–6h buildup) and later (24–36h drainage/recession) so pooling can "
            "grow and recede; native 1h MRMS (or 15-min) forcing would reduce blend-only motion."
        ),
    }

    precip_meta = {
        "frames": precip_frames,
        "storm_total_png": total_png,
        "storm_total_max_mm": float(np.nanmax(total)) if np.isfinite(total).any() else None,
        "bounds": leaflet,
        "extent": EXTENT_ID,
        "soft_edge": True,
        "land_mask": True,
        "colorbar": {"cmap": PRECIP_CMAP, "units": "mm", "label": "MRMS QPE (mm)"},
        "opacity_default": 0.72,
        "approx_resolution_km": 1.0,
        "loop_note": "Metro soft-edge MRMS: native 6h densified with 1h temporal blends",
        "time_window": time_window,
    }
    susc_meta = {
        "frames": susc_frames,
        "bounds": leaflet,
        "extent": EXTENT_ID,
        "soft_edge": True,
        "formula": FORMULA,
        "disclaimer": (
            "Screening index (weather evolves; landscape/infra mostly static). "
            "Not flood probability / not depth. Soft metro land+edge mask."
        ),
        "colorbar": {"cmap": SUSC_CMAP, "units": "index 0–1", "label": "Susceptibility (screening)"},
        "opacity_default": 0.55,
        "time_window": time_window,
    }

    radar_meta = {
        "n_paths": 3,
        "default_storm_path": "mrms_qpe_ida",
        "n_loop_frames_default": len(precip_frames),
        "step_note": "MRMS metro soft-edge: native 6h + 1h temporal blends; depth cum at 6/12/18/24h",
        "susceptibility_formula": FORMULA,
        "product_policy": "ida_hires_viz_with_earth2_scenarios",
        "extent": EXTENT_ID,
        "soft_edge": True,
        "time_window": time_window,
    }
    (ASSETS / "radar_stack_meta.json").write_text(json.dumps(radar_meta, indent=2))

    # Patch product manifests in place (preserve Earth2 scenario paths)
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        paths = m.get("storm_paths") or []
        updated = False
        for p in paths:
            if p.get("id") != "mrms_qpe_ida" and not p.get("ida_primary_viz"):
                continue
            p["precip"] = precip_meta
            p["susceptibility"] = susc_meta
            p["extent"] = EXTENT_ID
            p["honesty"] = (
                "PRIMARY Ida storm visualization (~1 km MRMS QPE) on continuous metro domain with "
                "soft land+edge alpha (no hard citywide crop). Temporal 1h blends densify the loop. "
                "NOT NEXRAD reflectivity tiles; NOT an official NWS flood warning."
            )
            updated = True
        if not updated and paths:
            # Fallback: treat first primary as MRMS
            for p in paths:
                if p.get("primary"):
                    p["precip"] = precip_meta
                    p["susceptibility"] = susc_meta
                    break
        # Top-level convenience copies (legacy consumers)
        m["precip"] = precip_meta
        m["susceptibility"] = susc_meta
        m["time_window"] = time_window
        lb = m.get("layer_bounds") or {}
        lb.update(
            {
                "map_extent_default": EXTENT_ID,
                "data_domain": EXTENT_ID,
                "data_domain_bounds": leaflet,
                "precip": leaflet,
                "susceptibility": leaflet,
                "inundation": leaflet,
                "note": "metro = continuous soft-edge overlays; citywide legacy retired for Ida viz",
            }
        )
        m["layer_bounds"] = lb
        mp.write_text(json.dumps(m, indent=2))

    # Ensure inundation cumulative_frames prefer metro PNG names when present
    for meta_name in ("inundation_meta.json", "depth_metro_mrms_qpe_ida_meta.json", "depth_citywide_mrms_qpe_ida_meta.json"):
        mp = ASSETS / meta_name
        if not mp.exists():
            continue
        meta = json.loads(mp.read_text())
        cum = meta.get("cumulative_frames") or []
        for fr in cum:
            lead = int(fr.get("lead_hours") or 0)
            metro_png = f"depth_metro_mrms_cum_lead_{lead:02d}h_m.png"
            if (ASSETS / metro_png).exists():
                fr["png"] = metro_png
                fr["evolves_with_timeline"] = True
        st = meta.get("storm_total") or {}
        if (ASSETS / "depth_metro_mrms_qpe_ida_storm_total_m.png").exists():
            st["png"] = "depth_metro_mrms_qpe_ida_storm_total_m.png"
        meta["storm_total"] = st
        meta["bounds"] = leaflet
        meta["extent"] = EXTENT_ID
        meta["time_window"] = time_window
        meta["depth_timeline_note"] = (
            "Cumulative depth frames at +6/+12/+18/+24h (HAND after drainage proxy). "
            "Product map swaps nearest cum frame with precip lead; early leads are dry/near-dry."
        )
        mp.write_text(json.dumps(meta, indent=2))

    # Mirror inundation into product manifests
    inundation_path = ASSETS / "inundation_meta.json"
    if inundation_path.exists():
        inundation = json.loads(inundation_path.read_text())
        for name in ("product_manifest.json", "manifest.json"):
            mp = ASSETS / name
            if not mp.exists():
                continue
            m = json.loads(mp.read_text())
            m["inundation"] = inundation
            if m.get("inundation_citywide"):
                m["inundation_citywide"]["png"] = (inundation.get("storm_total") or {}).get(
                    "png", m["inundation_citywide"].get("png")
                )
                m["inundation_citywide"]["bounds"] = leaflet
                m["inundation_citywide"]["extent"] = EXTENT_ID
            mp.write_text(json.dumps(m, indent=2))

    out = {
        "extent": EXTENT_ID,
        "n_frames": len(precip_frames),
        "bounds": leaflet,
        "soft_edge_px": FEATHER_PX,
        "display_shape": list(DISPLAY_SHAPE),
        "time_window": time_window,
        "vmax_interval_mm": vmax,
    }
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
