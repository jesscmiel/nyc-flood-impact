#!/usr/bin/env python3
"""Build Earth2 radar stack: denser loop, multi-factor susceptibility, alt storm paths.

- Primary path: Earth2 control / member 0
- Alternate path: Earth2 ensemble member 1 (IC perturbation) when available
- Temporal density: 2h blends between native 6h leads (labeled temporal_blend)
- Susceptibility: weather × landscape × infrastructure (documented screening)
- No MRMS in the product UI
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds, rowcol
from rasterio.warp import reproject

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_multifactor_susceptibility import FORMULA, build_static_factors, combine_frame  # noqa: E402
from rebuild_citywide_layers import _render_nearest_to_extent  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
E2_DIR = PROCESSED_DIR / "earth2_precip"
SUSC_DIR = PROCESSED_DIR / "susceptibility"
EXTENT_ID = "citywide"
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]
DISPLAY_SHAPE = (360, 480)
PRECIP_CMAP = "turbo"
SUSC_CMAP = "YlOrRd"


def _rgba_precip(values: np.ndarray, vmax: float, opacity: int = 210) -> np.ndarray:
    finite = np.isfinite(values) & (values > 0.05)
    data = np.where(np.isfinite(values), values, 0.0).astype(np.float32)
    vmax = max(float(vmax), 1e-6)
    normalized = np.clip(data / vmax, 0.0, 1.0)
    rgba = colormaps[PRECIP_CMAP](normalized, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(opacity, 50 + (normalized * 190).astype(np.uint8)), 0)
    return rgba


def _rgba_susc(values: np.ndarray, opacity: int = 200) -> np.ndarray:
    finite = np.isfinite(values) & (values > 0.04)
    data = np.clip(np.where(np.isfinite(values), values, 0.0), 0, 1).astype(np.float32)
    rgba = colormaps[SUSC_CMAP](data, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(opacity, 40 + (data * 180).astype(np.uint8)), 0)
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


def _load_member(clipped: Path, member: int = 0) -> tuple[list[dict], np.ndarray, np.ndarray, float]:
    with xr.open_dataset(clipped) as ds:
        precip = ds["precipitation_mm"]
        if "ensemble" in precip.dims:
            n = precip.sizes["ensemble"]
            member = min(member, n - 1)
            precip = precip.isel(ensemble=member)
        lat = precip.lat.values.astype(np.float64)
        lon = precip.lon.values.astype(np.float64)
        leads = [float(v) for v in precip.lead_time_hours.values]
        valids = [np.datetime64(v, "m") for v in precip.valid_time.values]
        fields = []
        for i, (lead, valid) in enumerate(zip(leads, valids)):
            field = precip.isel(lead_time_hours=i).values.astype(np.float32)
            fields.append(
                {
                    "lead_hours": float(lead),
                    "valid_time": str(valid),
                    "field": field,
                    "native": True,
                    "temporal_blend": False,
                }
            )
        vmax = float(np.nanmax([np.nanmax(f["field"]) for f in fields]))
    return fields, lat, lon, vmax


def _blend_stack(native: list[dict], step_hours: float = 2.0) -> list[dict]:
    """Insert temporal blends every step_hours between native 6h frames."""
    if len(native) < 2:
        return native
    out: list[dict] = []
    for i, left in enumerate(native):
        out.append(left)
        if i == len(native) - 1:
            break
        right = native[i + 1]
        dt = right["lead_hours"] - left["lead_hours"]
        n_steps = int(round(dt / step_hours))
        if n_steps <= 1:
            continue
        left_t = np.datetime64(left["valid_time"])
        right_t = np.datetime64(right["valid_time"])
        for k in range(1, n_steps):
            alpha = k / n_steps
            mid_lead = left["lead_hours"] + dt * alpha
            mid_t = left_t + (right_t - left_t) * alpha
            blended = (1 - alpha) * left["field"] + alpha * right["field"]
            out.append(
                {
                    "lead_hours": float(mid_lead),
                    "valid_time": str(np.datetime64(mid_t, "m")),
                    "field": blended.astype(np.float32),
                    "native": False,
                    "temporal_blend": True,
                    "blend_of": [left["lead_hours"], right["lead_hours"]],
                    "blend_alpha": alpha,
                }
            )
    out.sort(key=lambda f: f["lead_hours"])
    return out


def _infra_highlights(precip, susc, transform, roads_path: Path, out_path: Path) -> dict:
    if not roads_path.exists():
        return {"n_features": 0, "path": None}
    roads = json.loads(roads_path.read_text())
    h, w = precip.shape
    feats = []
    finite = precip[np.isfinite(precip)]
    p75 = float(np.nanpercentile(finite, 75)) if finite.size else 1.0
    for feat in roads.get("features", [])[:4000]:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords:
            continue
        if geom.get("type") == "LineString":
            mid = coords[len(coords) // 2]
            lon, lat = mid[0], mid[1]
        elif geom.get("type") == "Point":
            lon, lat = coords[0], coords[1]
        else:
            continue
        try:
            r, c = rowcol(transform, lon, lat)
        except Exception:
            continue
        r, c = int(r), int(c)
        if not (0 <= r < h and 0 <= c < w):
            continue
        p, s = precip[r, c], susc[r, c]
        if not np.isfinite(p) or not np.isfinite(s):
            continue
        score = float(p / max(p75, 1e-6) * s)
        if score < 0.35 or p < max(1.0, 0.25 * p75):
            continue
        props = dict(feat.get("properties") or {})
        props.update(
            {
                "highlight_score": round(score, 3),
                "precip_mm": round(float(p), 2),
                "susceptibility": round(float(s), 3),
                "demo_only": True,
                "note": "Storm-synced highlight from multi-factor susceptibility — not a closure order.",
            }
        )
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return {"n_features": len(feats), "path": out_path.name}


def _warp_factor(path: Path, shape, transform) -> np.ndarray:
    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    return dst


def _export_path(
    path_id: str,
    label: str,
    scenario_kind: str,
    clipped: Path,
    member: int,
    landscape: np.ndarray,
    infra: np.ndarray,
    transform,
    roads_path: Path,
    primary: bool,
) -> dict:
    print(f"Exporting storm path {path_id} (member={member})…")
    native, lat, lon, vmax = _load_member(clipped, member=member)
    stack = _blend_stack(native, step_hours=2.0)
    print(f"  native={len(native)} denser={len(stack)} vmax={vmax:.2f}")

    prefix = "" if primary else f"{path_id}_"
    precip_frames, susc_frames, infra_frames = [], [], []

    for i, fr in enumerate(stack):
        display, _, _ = _render_nearest_to_extent(fr["field"], lat, lon, BOUNDS, DISPLAY_SHAPE)
        lead = fr["lead_hours"]
        if fr["temporal_blend"]:
            stem = f"{prefix}precip_lead_{int(round(lead)):02d}h_blend"
        else:
            stem = f"{prefix}precip_lead_{int(round(lead)):02d}h"

        _write_tif(E2_DIR / f"{stem}.tif", display, transform)
        _write_png(ASSETS / f"{stem}.png", _rgba_precip(display, vmax=max(vmax, 5.0)))

        pnorm = np.clip(np.nan_to_num(display, nan=0.0) / max(vmax, 1e-6), 0, 1)
        susc = combine_frame(landscape, infra, pnorm)
        susc = np.where(np.isfinite(landscape), susc, np.nan)
        susc_stem = stem.replace("precip_", "susc_")
        _write_tif(SUSC_DIR / f"{susc_stem}.tif", susc, transform)
        _write_png(ASSETS / f"{susc_stem}.png", _rgba_susc(susc))

        infra_name = stem.replace("precip_", "infra_") + ".geojson"
        infra_meta = _infra_highlights(display, susc, transform, roads_path, ASSETS / infra_name)

        valid = fr["valid_time"].replace(" ", "T")[:16]
        precip_frames.append(
            {
                "index": i,
                "lead_hours": lead,
                "valid_time": valid,
                "png": f"{stem}.png",
                "tif": str(E2_DIR / f"{stem}.tif"),
                "mean_mm": float(np.nanmean(fr["field"])),
                "max_mm": float(np.nanmax(fr["field"])),
                "native": fr["native"],
                "temporal_blend": fr["temporal_blend"],
                "blend_of": fr.get("blend_of"),
                "native_shape": list(fr["field"].shape),
            }
        )
        susc_frames.append(
            {
                "index": i,
                "lead_hours": lead,
                "valid_time": valid,
                "png": f"{susc_stem}.png",
                "tif": str(SUSC_DIR / f"{susc_stem}.tif"),
                "mean": float(np.nanmean(susc)),
                "p90": float(np.nanpercentile(susc[np.isfinite(susc)], 90)) if np.isfinite(susc).any() else None,
                "formula": FORMULA,
            }
        )
        infra_frames.append(
            {"index": i, "lead_hours": lead, "geojson": infra_meta.get("path"), "n_features": infra_meta.get("n_features", 0)}
        )

    native_fields = [f["field"] for f in native]
    total_native = np.sum(np.stack(native_fields), axis=0).astype(np.float32)
    display_total, _, _ = _render_nearest_to_extent(total_native, lat, lon, BOUNDS, DISPLAY_SHAPE)
    total_png = f"{prefix}precip_storm_total.png"
    _write_tif(E2_DIR / f"{prefix}precip_storm_total.tif", display_total, transform)
    _write_png(ASSETS / total_png, _rgba_precip(display_total, vmax=max(float(np.nanmax(total_native)), 10.0)))

    leaflet_bounds = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    return {
        "id": path_id,
        "label": label,
        "scenario_kind": scenario_kind,
        "primary": primary,
        "source_file": str(clipped),
        "ensemble_member": member,
        "honesty": "Earth2 AI precip on ~0.25° grid — not NEXRAD. Temporal blends are mid-interval mixes for loop smoothness.",
        "precip": {
            "frames": precip_frames,
            "storm_total_png": total_png,
            "storm_total_max_mm": float(np.nanmax(total_native)),
            "bounds": leaflet_bounds,
            "native_grid": {"n_lat": int(lat.size), "n_lon": int(lon.size), "lat": [float(x) for x in lat], "lon": [float(x) for x in lon]},
            "colorbar": {"cmap": PRECIP_CMAP, "units": "mm / interval", "label": "Earth2 precip (mm)"},
            "opacity_default": 0.75,
        },
        "susceptibility": {
            "frames": susc_frames,
            "bounds": leaflet_bounds,
            "formula": FORMULA,
            "disclaimer": "Multi-factor screening (weather × landscape × infrastructure) — not depth.",
            "colorbar": {"cmap": SUSC_CMAP, "units": "index 0–1", "label": "Susceptibility (screening)"},
            "opacity_default": 0.65,
        },
        "infra_highlights": {"frames": infra_frames},
    }


def _export_mrms_alt_path(landscape, infra, transform, roads_path: Path) -> dict | None:
    """Labeled higher-res Ida alternate scenario from MRMS Multi-Sensor QPE (~1 km).

    Not a live competing weather product in the UI — a documented alternate storm path
    when StormCast/CorrDiff cannot run (natten). Source: NOAA MRMS QPE for Ida remnants.
    """
    mrms_dir = PROCESSED_DIR / "mrms_qpe"
    leads = [6, 12, 18, 24]
    tifs = []
    for lead in leads:
        p = mrms_dir / f"mrms_qpe_lead_{lead:02d}h_citywide.tif"
        if not p.exists():
            p = mrms_dir / f"mrms_qpe_lead_{lead:02d}h.tif"
        if p.exists():
            tifs.append((lead, p))
    total_tif = mrms_dir / "mrms_qpe_storm_total.tif"
    if not tifs or not total_tif.exists():
        print("  MRMS alt path skipped — citywide QPE assets missing")
        return None

    print("Exporting higher-res Ida storm viz path (MRMS QPE ~1 km) with dense temporal blends…")
    prefix = "mrms_qpe_ida_"
    precip_frames, susc_frames, infra_frames = [], [], []
    native_fields: list[dict] = []
    for lead, path in tifs:
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float32)
            if src.nodata is not None:
                data = np.where(data == src.nodata, np.nan, data)
            display = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
            reproject(
                source=data,
                destination=display,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
                src_nodata=np.nan,
                dst_nodata=np.nan,
            )
        hour = 12 + lead
        day = 1 + hour // 24
        hour = hour % 24
        valid = f"2021-09-{day:02d}T{hour:02d}:00"
        native_fields.append(
            {
                "lead_hours": float(lead),
                "valid_time": valid,
                "field": display,
                "native": True,
                "temporal_blend": False,
            }
        )

    # Densify to 1h temporal blends between native 6h MRMS leads for a smoother loop.
    dense = _blend_stack(native_fields, step_hours=1.0)
    vmax = max(
        (float(np.nanmax(f["field"])) for f in dense if np.isfinite(f["field"]).any()),
        default=1.0,
    )
    fields = []
    for i, fr in enumerate(dense):
        display = fr["field"].astype(np.float32)
        fields.append(display)
        lead = fr["lead_hours"]
        if fr["temporal_blend"]:
            stem = f"{prefix}precip_lead_{int(round(lead)):02d}h_blend"
        else:
            stem = f"{prefix}precip_lead_{int(round(lead)):02d}h"
        _write_tif(E2_DIR / f"{stem}.tif", display, transform)
        _write_png(ASSETS / f"{stem}.png", _rgba_precip(display, vmax=max(vmax, 5.0)))
        pnorm = np.clip(np.nan_to_num(display, nan=0.0) / max(vmax, 1e-6), 0, 1)
        susc = combine_frame(landscape, infra, pnorm)
        susc = np.where(np.isfinite(landscape), susc, np.nan)
        susc_stem = stem.replace("precip_", "susc_")
        _write_tif(SUSC_DIR / f"{susc_stem}.tif", susc, transform)
        _write_png(ASSETS / f"{susc_stem}.png", _rgba_susc(susc))
        infra_name = stem.replace("precip_", "infra_") + ".geojson"
        infra_meta = _infra_highlights(display, susc, transform, roads_path, ASSETS / infra_name)
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
                "resolution_note": "~1 km MRMS Multi-Sensor QPE (radar+gauge) — Ida primary viz",
            }
        )
        susc_frames.append(
            {
                "index": i,
                "lead_hours": float(lead),
                "valid_time": fr["valid_time"],
                "png": f"{susc_stem}.png",
                "tif": str(SUSC_DIR / f"{susc_stem}.tif"),
                "mean": float(np.nanmean(susc)),
                "formula": FORMULA,
            }
        )
        infra_frames.append(
            {"index": i, "lead_hours": float(lead), "geojson": infra_meta.get("path"), "n_features": infra_meta.get("n_features", 0)}
        )

    with rasterio.open(total_tif) as src:
        total = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        reproject(
            source=src.read(1).astype(np.float32),
            destination=total,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    total_png = f"{prefix}precip_storm_total.png"
    _write_tif(E2_DIR / f"{prefix}precip_storm_total.tif", total, transform)
    _write_png(ASSETS / total_png, _rgba_precip(total, vmax=max(float(np.nanmax(total)), 10.0)))

    # Re-render precip PNGs with final vmax
    for fr, field in zip(precip_frames, fields):
        _write_png(ASSETS / fr["png"], _rgba_precip(field, vmax=max(vmax, 5.0)))

    leaflet_bounds = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    return {
        "id": "mrms_qpe_ida",
        "label": "MRMS QPE Ida (~1 km)",
        "scenario_kind": "ida_primary_hires_viz",
        "primary": True,
        "ida_primary_viz": True,
        "source": "NOAA MRMS Multi-Sensor QPE (radar-derived + gauge) — Hurricane Ida remnants 2021-09-01",
        "source_file": str(mrms_dir),
        "honesty": (
            "PRIMARY Ida storm visualization (~1 km MRMS QPE). Temporal 1h blends densify the loop. "
            "Earth2 remains available as a labeled AI scenario track. NOT NEXRAD reflectivity tiles; "
            "NOT an official NWS flood warning product. StormCast/CorrDiff blocked without natten."
        ),
        "precip": {
            "frames": precip_frames,
            "storm_total_png": total_png,
            "storm_total_max_mm": float(np.nanmax(total)) if np.isfinite(total).any() else None,
            "bounds": leaflet_bounds,
            "colorbar": {"cmap": PRECIP_CMAP, "units": "mm", "label": "MRMS QPE (mm)"},
            "opacity_default": 0.78,
            "approx_resolution_km": 1.0,
            "loop_note": "Native 6h MRMS leads densified with 1h temporal blends",
        },
        "susceptibility": {
            "frames": susc_frames,
            "bounds": leaflet_bounds,
            "formula": FORMULA,
            "disclaimer": "Screening with MRMS-forced weather factor — not depth.",
            "colorbar": {"cmap": SUSC_CMAP, "units": "index 0–1", "label": "Susceptibility (screening)"},
            "opacity_default": 0.65,
        },
        "infra_highlights": {"frames": infra_frames},
    }


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    E2_DIR.mkdir(parents=True, exist_ok=True)
    SUSC_DIR.mkdir(parents=True, exist_ok=True)

    control = PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_citywide.nc"
    if not control.exists():
        from rebuild_citywide_layers import clip_forecast_citywide

        control = clip_forecast_citywide()

    print("Building multi-factor static layers…")
    factors = build_static_factors(display_shape=DISPLAY_SHAPE)
    transform = from_bounds(
        BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"], DISPLAY_SHAPE[1], DISPLAY_SHAPE[0]
    )
    landscape = _warp_factor(Path(factors["paths"]["landscape"]), DISPLAY_SHAPE, transform)
    infra = _warp_factor(Path(factors["paths"]["infra"]), DISPLAY_SHAPE, transform)

    roads_path = ASSETS / "roads.geojson"
    if not roads_path.exists():
        alt = FIGURES_DIR / "ida_v0_assets" / "roads.geojson"
        if alt.exists():
            roads_path = alt

    paths = []
    # Earth2 file naming stays unprefixed (primary=True for paths); product role is scenario.
    earth2 = _export_path(
        "earth2_control",
        "Earth2 AI scenario",
        "earth2_scenario",
        control,
        0,
        landscape,
        infra,
        transform,
        roads_path,
        primary=True,
    )
    earth2["primary"] = False
    earth2["ida_primary_viz"] = False
    earth2["label"] = "Earth2 AI scenario"
    earth2["scenario_kind"] = "earth2_scenario"
    earth2["honesty"] = (
        "Earth2 AI precip scenario (~0.25°). For Ida storm visualization prefer MRMS QPE (~1 km). "
        "Not NEXRAD. Temporal blends densify the loop only."
    )
    paths.append(earth2)

    ens = PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_ens2_citywide.nc"
    if ens.exists():
        with xr.open_dataset(ens) as ds:
            n_mem = int(ds.sizes.get("ensemble", 1))
        if n_mem > 1:
            alt = _export_path(
                "earth2_ens1",
                "Earth2 alt path · member 1",
                "alternate_storm_path",
                ens,
                1,
                landscape,
                infra,
                transform,
                roads_path,
                primary=False,
            )
            paths.append(alt)

    # Ida primary viz: MRMS QPE ~1 km (StormCast/CorrDiff blocked without natten).
    mrms_viz = _export_mrms_alt_path(landscape, infra, transform, roads_path)
    if mrms_viz:
        paths.insert(0, mrms_viz)

    default_id = "mrms_qpe_ida" if mrms_viz else "earth2_control"
    default_path = next((p for p in paths if p["id"] == default_id), paths[0])
    leaflet_bounds = default_path["precip"]["bounds"]
    inundation_meta = ASSETS / "inundation_meta.json"
    inundation = json.loads(inundation_meta.read_text()) if inundation_meta.exists() else None
    manifest = {
        "product_policy": "ida_hires_viz_with_earth2_scenarios",
        "product_kind": "research_flood_warning_prototype",
        "note": (
            "For Hurricane Ida, default storm visualization is MRMS QPE (~1 km). "
            "Earth2 (+ ensemble) remain labeled AI scenario tracks. "
            "Depth/alerts are research prototypes — NOT official NWS flood warnings."
        ),
        "honesty": (
            "Research flood-warning prototype. NOT official NWS. NOT emergency guidance. "
            "MRMS QPE is radar+gauge QPE (~1 km), not NEXRAD reflectivity tiles."
        ),
        "default_storm_path": default_id,
        "storm_paths": paths,
        "precip": default_path["precip"],
        "susceptibility": {
            **default_path["susceptibility"],
            "static_factors": factors,
            "formula": FORMULA,
        },
        "infra_highlights": default_path.get("infra_highlights") or earth2["infra_highlights"],
        "inundation": inundation,
        "flood_warning_prototype": {
            "label": "Research flood-warning prototype",
            "official_nws": False,
            "engine_depth": "pysheds HAND + bathtub",
            "engine_sewer": "pyswmm available in env but no calibrated NYC DEP INP — thresholds use depth only",
            "thresholds_m": {"advisory": 0.03, "watch": 0.08, "warning": 0.15},
            "disclaimer": "Threshold chips are research heuristics on estimated depth — not NWS watch/warning criteria.",
        },
        "layer_bounds": {
            "map_extent_default": EXTENT_ID,
            "precip": leaflet_bounds,
            "susceptibility": leaflet_bounds,
            "inundation": (inundation or {}).get("bounds") or leaflet_bounds,
        },
        "mrms_qpe": None,
        "compare_mode": False,
        "stormcast": {
            "status": "skipped",
            "reason": "natten unavailable — see outputs/stormcast_corrdiff_attempt.json",
            "ida_hires_viz": "mrms_qpe_ida" if mrms_viz else None,
        },
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "radar_stack_meta.json").write_text(
        json.dumps(
            {
                "n_paths": len(paths),
                "default_storm_path": default_id,
                "n_loop_frames_default": len(default_path["precip"]["frames"]),
                "step_note": "MRMS: native 6h + 1h temporal blends; Earth2: native 6h + 2h blends",
                "susceptibility_formula": FORMULA,
                "product_policy": manifest["product_policy"],
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "n_paths": len(paths),
                "default": default_id,
                "n_frames": len(default_path["precip"]["frames"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
