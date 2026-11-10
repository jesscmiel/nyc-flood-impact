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
    primary = _export_path(
        "earth2_control",
        "Earth2 (primary)",
        "earth2_primary",
        control,
        0,
        landscape,
        infra,
        transform,
        roads_path,
        primary=True,
    )
    paths.append(primary)

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

    # Manifest: primary precip at top level for backward compatibility + storm_paths list
    leaflet_bounds = primary["precip"]["bounds"]
    manifest = {
        "product_policy": "earth2_primary_with_alt_storm_paths",
        "note": (
            "Primary path is Earth2. Alternate Earth2 ensemble members are optional scenario tracks — "
            "not MRMS/NEXRAD and not a validation split-screen."
        ),
        "honesty": "AI 6h accumulations on ~0.25°. Temporal blends densify the loop only. Not radar reflectivity.",
        "default_storm_path": "earth2_control",
        "storm_paths": paths,
        "precip": primary["precip"],
        "susceptibility": {
            **primary["susceptibility"],
            "static_factors": factors,
            "formula": FORMULA,
        },
        "infra_highlights": primary["infra_highlights"],
        "layer_bounds": {
            "map_extent_default": EXTENT_ID,
            "precip": leaflet_bounds,
            "susceptibility": leaflet_bounds,
        },
        "mrms_qpe": None,
        "compare_mode": False,
        "stormcast": {"status": "skipped", "reason": "natten unavailable"},
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "radar_stack_meta.json").write_text(
        json.dumps(
            {
                "n_paths": len(paths),
                "n_loop_frames_primary": len(primary["precip"]["frames"]),
                "step_note": "Native 6h + 2h temporal blends",
                "susceptibility_formula": FORMULA,
                "product_policy": manifest["product_policy"],
            },
            indent=2,
        )
    )
    print(json.dumps({"n_paths": len(paths), "n_frames": len(primary["precip"]["frames"])}, indent=2))


if __name__ == "__main__":
    main()
