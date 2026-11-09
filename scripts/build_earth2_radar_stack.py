#!/usr/bin/env python3
"""Build Earth2-only denser radar stack + time-varying susceptibility.

- Temporal density: native 6h Earth2 accumulations plus mid-interval blends
  (honestly labeled temporal_blend) so the product loop feels smoother.
- Susceptibility frames: f(static terrain/NLCD screening × frame precip).
- Infra highlight GeoJSON per frame where precip × susceptibility is elevated.
- No MRMS / other precip sources.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from matplotlib import colormaps
from PIL import Image
from rasterio.transform import from_bounds, xy
from rasterio.warp import reproject
from rasterio.enums import Resampling

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS
from nyc_flash_flood_case_study.pluvial import build_pluvial_screening

ASSETS = FIGURES_DIR / "product_assets"
E2_DIR = PROCESSED_DIR / "earth2_precip"
SUSC_DIR = PROCESSED_DIR / "susceptibility"
EXTENT_ID = "citywide"
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]
DISPLAY_SHAPE = (360, 480)

# Radar-ish precip ramp (not NEXRAD reflectivity — accumulation mm display only).
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


def _load_native_frames(clipped: Path) -> tuple[list[dict], np.ndarray, np.ndarray, float]:
    with xr.open_dataset(clipped) as ds:
        precip = ds["precipitation_mm"]
        if "ensemble" in precip.dims:
            precip = precip.isel(ensemble=0)
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
        vmax = float(np.nanmax(precip.values))
    return fields, lat, lon, vmax


def _blend_stack(native: list[dict], step_hours: float = 3.0) -> list[dict]:
    """Insert mid-interval linear blends between native 6h frames for a denser loop."""
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
        # One midpoint blend (e.g. 6→12 becomes +9h).
        alpha = 0.5
        mid_lead = left["lead_hours"] + dt * alpha
        # Approximate valid time as midpoint.
        left_t = np.datetime64(left["valid_time"])
        right_t = np.datetime64(right["valid_time"])
        mid_t = left_t + (right_t - left_t) / 2
        blended = (1 - alpha) * left["field"] + alpha * right["field"]
        out.append(
            {
                "lead_hours": float(mid_lead),
                "valid_time": str(np.datetime64(mid_t, "m")),
                "field": blended.astype(np.float32),
                "native": False,
                "temporal_blend": True,
                "blend_of": [left["lead_hours"], right["lead_hours"]],
            }
        )
    out.sort(key=lambda f: f["lead_hours"])
    return out


def _render_nearest(field: np.ndarray, lat: np.ndarray, lon: np.ndarray):
    from rebuild_citywide_layers import _render_nearest_to_extent

    return _render_nearest_to_extent(field, lat, lon, BOUNDS, DISPLAY_SHAPE)


def _warp_to(src_path: Path, shape: tuple[int, int], transform) -> np.ndarray:
    dst = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
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


def _infra_highlights(precip: np.ndarray, susc: np.ndarray, transform, roads_path: Path, out_path: Path) -> dict:
    if not roads_path.exists():
        return {"n_features": 0, "path": None}
    roads = json.loads(roads_path.read_text())
    h, w = precip.shape
    feats = []
    # Threshold: high precip relative to frame + elevated susceptibility
    p95 = float(np.nanpercentile(precip[np.isfinite(precip)], 75)) if np.isfinite(precip).any() else 1.0
    for feat in roads.get("features", [])[:4000]:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords:
            continue
        # Sample midpoint of linestring
        if geom.get("type") == "LineString":
            mid = coords[len(coords) // 2]
            lon, lat = mid[0], mid[1]
        elif geom.get("type") == "Point":
            lon, lat = coords[0], coords[1]
        else:
            continue
        # row/col
        # Affine: x = a*c + ... use rasterio
        from rasterio.transform import rowcol

        try:
            r, c = rowcol(transform, lon, lat)
        except Exception:
            continue
        r, c = int(r), int(c)
        if not (0 <= r < h and 0 <= c < w):
            continue
        p = precip[r, c]
        s = susc[r, c]
        if not np.isfinite(p) or not np.isfinite(s):
            continue
        score = float(p / max(p95, 1e-6) * s)
        if score < 0.35 or p < max(1.0, 0.25 * p95):
            continue
        props = dict(feat.get("properties") or {})
        props.update(
            {
                "highlight_score": round(score, 3),
                "precip_mm": round(float(p), 2),
                "susceptibility": round(float(s), 3),
                "demo_only": True,
                "note": "Infra highlight from Earth2 precip × susceptibility — not a closure order.",
            }
        )
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    fc = {"type": "FeatureCollection", "features": feats}
    out_path.write_text(json.dumps(fc))
    return {"n_features": len(feats), "path": out_path.name}


def main() -> None:
    clipped = PROJECT_ROOT / "data" / "forecasts" / "nyc_precip_ida_citywide.nc"
    if not clipped.exists():
        from rebuild_citywide_layers import clip_forecast_citywide

        clipped = clip_forecast_citywide()

    print("Loading native Earth2 frames…")
    native, lat, lon, vmax = _load_native_frames(clipped)
    stack = _blend_stack(native, step_hours=3.0)
    print(f"  native={len(native)} denser={len(stack)} vmax={vmax:.2f} mm")

    print("Building static pluvial base (terrain + NLCD)…")
    base_meta = build_pluvial_screening(extent_id=EXTENT_ID, assets_dir=ASSETS)
    base_tif = Path(base_meta["tif"])

    E2_DIR.mkdir(parents=True, exist_ok=True)
    SUSC_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    transform = from_bounds(
        BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"], DISPLAY_SHAPE[1], DISPLAY_SHAPE[0]
    )
    # Warp base susceptibility to precip display grid for coupling.
    base_susc_full = None
    with rasterio.open(base_tif) as src:
        base_hi = src.read(1).astype(np.float32)
        base_hi = np.where(base_hi == src.nodata, np.nan, base_hi)
        base_susc_full = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        reproject(
            source=base_hi,
            destination=base_susc_full,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )

    roads_path = ASSETS / "roads.geojson"
    if not roads_path.exists():
        alt = FIGURES_DIR / "ida_v0_assets" / "roads.geojson"
        if alt.exists():
            roads_path = alt

    precip_frames = []
    susc_frames = []
    infra_frames = []
    for i, fr in enumerate(stack):
        display, tf, geo = _render_nearest(fr["field"], lat, lon)
        # Use citywide display transform consistently
        tf = transform
        lead = fr["lead_hours"]
        lead_tag = f"{lead:05.1f}".replace(".", "p")
        stem = f"precip_lead_{int(lead):02d}h" if fr["native"] and float(lead).is_integer() else f"precip_lead_{lead_tag}h"
        # Prefer clean names for native integers
        if fr["native"] and abs(lead - round(lead)) < 1e-6:
            stem = f"precip_lead_{int(round(lead)):02d}h"
        else:
            stem = f"precip_lead_{int(round(lead)):02d}h_blend"

        # Avoid collisions for blends: use unique blend stem
        if fr["temporal_blend"]:
            stem = f"precip_lead_{int(round(lead)):02d}h_blend"

        _write_tif(E2_DIR / f"{stem}.tif", display, tf)
        _write_png(ASSETS / f"{stem}.png", _rgba_precip(display, vmax=max(vmax, 5.0)))

        # Time-varying susceptibility: base × precip factor
        pnorm = np.clip(np.nan_to_num(display, nan=0.0) / max(vmax, 1e-6), 0, 1)
        # susc = base * (0.30 + 0.70 * precip_norm) — precip modulates screening
        susc = np.clip(base_susc_full * (0.30 + 0.70 * pnorm), 0, 1).astype(np.float32)
        susc = np.where(np.isfinite(base_susc_full), susc, np.nan)
        susc_stem = stem.replace("precip_", "susc_")
        _write_tif(SUSC_DIR / f"{susc_stem}.tif", susc, tf)
        _write_png(ASSETS / f"{susc_stem}.png", _rgba_susc(susc))

        infra_name = stem.replace("precip_", "infra_") + ".geojson"
        infra_meta = _infra_highlights(display, susc, tf, roads_path, ASSETS / infra_name)

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
                "formula": "base_pluvial * (0.30 + 0.70 * precip_norm)",
            }
        )
        infra_frames.append(
            {
                "index": i,
                "lead_hours": lead,
                "geojson": infra_meta.get("path"),
                "n_features": infra_meta.get("n_features", 0),
            }
        )
        print(f"  frame +{lead}h native={fr['native']} infra={infra_meta.get('n_features', 0)}")

    # Storm total (native sum only)
    native_fields = [f["field"] for f in native]
    total_native = np.sum(np.stack(native_fields), axis=0).astype(np.float32)
    display_total, _, _ = _render_nearest(total_native, lat, lon)
    _write_tif(E2_DIR / "precip_storm_total.tif", display_total, transform)
    _write_png(ASSETS / "precip_storm_total.png", _rgba_precip(display_total, vmax=max(float(np.nanmax(total_native)), 10.0)))

    leaflet_bounds = [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]
    manifest = {
        "product_policy": "earth2_only",
        "note": "Earth2 precip only — no MRMS/NEXRAD/other precip sources in the product UI.",
        "honesty": "AI 6h accumulations on ~0.25° grid. Temporal blend frames are mid-interval linear mixes for smoother loop — not extra model output, not radar reflectivity.",
        "precip": {
            "init_time": "2021-09-01T12:00",
            "forecast_model": "FourCastNet + PrecipitationAFNO",
            "frames": precip_frames,
            "storm_total_png": "precip_storm_total.png",
            "storm_total_tif": str(E2_DIR / "precip_storm_total.tif"),
            "storm_total_max_mm": float(np.nanmax(total_native)),
            "bounds": leaflet_bounds,
            "native_grid": {
                "n_lat": int(lat.size),
                "n_lon": int(lon.size),
                "lat": [float(x) for x in lat],
                "lon": [float(x) for x in lon],
            },
            "colorbar": {"cmap": PRECIP_CMAP, "units": "mm / interval", "label": "Earth2 precip (mm)"},
            "opacity_default": 0.75,
        },
        "susceptibility": {
            "static_png": "pluvial_screening.png",
            "static_meta": base_meta,
            "frames": susc_frames,
            "bounds": leaflet_bounds,
            "formula": "base_pluvial(terrain+NLCD) * (0.30 + 0.70 * precip_norm)",
            "disclaimer": "Screening index only — not inundation depth.",
            "colorbar": {"cmap": SUSC_CMAP, "units": "index 0–1", "label": "Susceptibility (screening)"},
            "opacity_default": 0.65,
        },
        "infra_highlights": {
            "frames": infra_frames,
            "note": "Roads highlighted where Earth2 precip × susceptibility is elevated — demo sync only.",
        },
        "layer_bounds": {
            "map_extent_default": EXTENT_ID,
            "precip": leaflet_bounds,
            "susceptibility": leaflet_bounds,
        },
        "mrms_qpe": None,
        "compare_mode": False,
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
    (ASSETS / "radar_stack_meta.json").write_text(
        json.dumps(
            {
                "n_native": len(native),
                "n_loop_frames": len(stack),
                "step_note": "Native 6h frames + mid-interval temporal blends",
                "product_policy": "earth2_only",
            },
            indent=2,
        )
    )
    print(json.dumps({"n_frames": len(stack), "vmax": vmax, "assets": str(ASSETS)}, indent=2))


if __name__ == "__main__":
    main()
