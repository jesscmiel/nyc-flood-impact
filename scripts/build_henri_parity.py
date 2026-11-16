#!/usr/bin/env python3
"""Full Henri parity for Decision Desk Event picker (audit V5 / P0.8 + P2.2).

Rebuilds from cached metro Henri MRMS + HAND depth (no re-fetch required):
  - Official-inventory Decision Desk JSON/GeoJSON
  - Soft-edge MRMS precip + susceptibility radar loop (0–24h)
  - Depth cum / storm-total PNGs
  - Shortlist bundle with same official IDs as Ida
  - Ida↔Henri same-ID compare strip
  - Manifest + product_map.html unhide Event picker

Research only — NOT NWS / NOT decision-grade.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
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

from build_multifactor_susceptibility import FORMULA, combine_frame  # noqa: E402
from flood_risk.risk.decision_classes import is_decision_class_asset  # noqa: E402
from flood_risk.risk.demo_shortlist import demo_shortlist_ids  # noqa: E402
from flood_risk.risk.ranked_assets import build_ranked_assets, write_ranked_assets  # noqa: E402
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
)
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402
from rebuild_metro_radar_viz import (  # noqa: E402
    DISPLAY_SHAPE,
    PRECIP_CMAP,
    SUSC_CMAP,
    _load_land_fade,
    _rgba_precip,
    _rgba_susc,
    _warp_to_display,
)

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
MRMS_DIR = PROCESSED_DIR / "mrms_qpe_metro_henri"
E2_DIR = PROCESSED_DIR / "earth2_precip"
SUSC_DIR = PROCESSED_DIR / "susceptibility"
BOUNDS = EXTENTS[PRIMARY_DATA_EXTENT]["bounds"]

INIT = datetime(2021, 8, 21, 18, 0, tzinfo=timezone.utc)
LEAD_MAX = 24
CUM_LEADS = (6, 12, 18, 24)
PREFIX = "mrms_qpe_henri_"
DEPTH_CMAP = "Blues"
MIN_DEPTH_M = 0.001
STORM_PATH_ID = "mrms_qpe_henri"


def _leaflet_bounds() -> list:
    return [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]]


def _display_transform():
    return from_bounds(
        BOUNDS["xmin"],
        BOUNDS["ymin"],
        BOUNDS["xmax"],
        BOUNDS["ymax"],
        DISPLAY_SHAPE[1],
        DISPLAY_SHAPE[0],
    )


def _valid_time(lead_hours: float) -> str:
    ts = INIT + timedelta(hours=float(lead_hours))
    return ts.strftime("%Y-%m-%dT%H:%M")


def _write_png(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)


def _write_tif_display(path: Path, data: np.ndarray, transform) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
        compress="deflate",
    ) as dst:
        dst.write(np.where(np.isfinite(data), data, -9999.0).astype(np.float32), 1)


def _rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def require_cached_inputs() -> dict:
    storm = MRMS_DIR / "mrms_qpe_metro_henri_storm_total.tif"
    depth = INUN / "depth_metro_mrms_qpe_henri_storm_total_m.tif"
    gpkg = ASSETS / "exposure_citywide.gpkg"
    missing = [str(p) for p in (storm, depth, gpkg) if not p.exists()]
    if missing:
        raise SystemExit(
            "Henri parity needs cached MRMS/depth/exposure. Missing:\n  - "
            + "\n  - ".join(missing)
            + "\nRun scripts/build_second_storm_desk.py first if MRMS hours are fetchable."
        )
    hours_ok = []
    for lead in range(0, LEAD_MAX + 1):
        if (MRMS_DIR / f"mrms_qpe_metro_henri_1h_lead_{lead:02d}h.tif").exists():
            hours_ok.append(lead)
    if len(hours_ok) < 6:
        raise SystemExit(f"too few Henri hourly MRMS frames ({len(hours_ok)})")
    lead_tifs = []
    for lead in CUM_LEADS:
        p = INUN / f"depth_metro_mrms_henri_cum_lead_{lead:02d}h_m.tif"
        if p.exists():
            lead_tifs.append((float(lead), p))
    return {
        "storm_total_tif": storm,
        "depth_tif": depth,
        "gpkg": gpkg,
        "hours_ok": hours_ok,
        "lead_tifs": lead_tifs,
    }


def rebuild_henri_desk(cache: dict) -> dict:
    print("Building Henri desk on official inventory × cached HAND depth…")
    payload = build_ranked_assets(
        gpkg=cache["gpkg"],
        depth_tif=cache["depth_tif"],
        lead_tifs=cache["lead_tifs"],
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
        "inventory": "official_mta_gtfs_facilities_uid",
    }
    payload["honesty"] = (
        "Henri research desk via MRMS×HAND × official inventory — NOT NWS / NOT decision-grade. "
        "Lead chips use 6/12/18/24h cum frames for this event. Same asset IDs as Ida shortlist."
    )
    payload["event_id"] = "henri-2021"
    payload["schema_version"] = payload.get("schema_version") or "1.1.0"
    out_json = ASSETS / "decision_desk_assets_henri.json"
    out_geo = ASSETS / "decision_desk_assets_henri.geojson"
    shortlist = demo_shortlist_ids()
    by_id = {a["id"]: a for a in payload["assets"]}
    mapped = [by_id[i] for i in shortlist if i in by_id]
    missing = [i for i in shortlist if i not in by_id]
    # Event-scoped dry stubs keep shortlist IDs aligned with Ida when Henri is below band.
    ida_desk_path = ASSETS / "decision_desk_assets.json"
    ida_by = {}
    if ida_desk_path.exists():
        ida_by = {a["id"]: a for a in json.loads(ida_desk_path.read_text()).get("assets") or []}
    dry_stubs: list[dict] = []
    for aid in missing:
        src = ida_by.get(aid)
        if not src:
            continue
        stub = {
            "id": aid,
            "name": src.get("name"),
            "asset_type": src.get("asset_type"),
            "layer": src.get("layer"),
            "max_depth_m": 0.0,
            "max_depth_cm": 0.0,
            "band": "below_band",
            "band_label": "dry / <3 cm",
            "band_full_label": "Below research ponding band on Henri (event-scoped)",
            "first_exceedance_lead_h": None,
            "first_exceedance_note": "Below HAND band on Henri remnants — still listed for Ida↔Henri ID continuity.",
            "action_hint": "Henri research depth below ponding band at this official ID — not a closure signal.",
            "lon": src.get("lon"),
            "lat": src.get("lat"),
            "highway": src.get("highway"),
            "facility_type": src.get("facility_type"),
            "structure": src.get("structure"),
            "gtfs_stop_id": src.get("gtfs_stop_id"),
            "uid": src.get("uid"),
            "inventory_source": src.get("inventory_source"),
            "engine": "pysheds_hand_bathtub_v2",
            "rank": None,
            "event_scoped": "henri_below_band",
            "henri_dry_stub": True,
            "nyc_demo_geography": src.get("nyc_demo_geography", True),
        }
        dry_stubs.append(stub)
        by_id[aid] = stub
        payload["assets"].append(stub)
    tops = [a for a in payload["assets"] if is_decision_class_asset(a) and not a.get("henri_dry_stub")][:100]
    seen: set[str] = set()
    bundled = []
    ordered_shortlist = [by_id[i] for i in shortlist if i in by_id]
    for a in ordered_shortlist + tops:
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        bundled.append(a)
    bundle = {
        "product": payload.get("product"),
        "schema_version": payload.get("schema_version"),
        "bundle": "shortlist_top100_henri",
        "event_id": "henri-2021",
        "honesty": payload["honesty"],
        "official_nws": False,
        "decision_grade": False,
        "shortlist_ids": list(shortlist),
        "shortlist_ids_present": [a["id"] for a in mapped],
        "shortlist_ids_below_band": [a["id"] for a in dry_stubs],
        "shortlist_ids_missing": [i for i in shortlist if i not in by_id],
        "counts": payload.get("counts"),
        "band_action_hints": payload.get("band_action_hints"),
        "assets": bundled,
        "listed_n": len(bundled),
        "full_desk_json": "decision_desk_assets_henri.json",
        "note": (
            "Henri shortlist uses the same official inventory IDs as Ida. "
            "Assets below the HAND ponding band are labeled dry stubs for Event continuity."
        ),
    }
    # Rewrite full Henri desk JSON so dry stubs are findable in All mode too.
    write_ranked_assets(payload, out_json, out_geo)
    (OUTPUTS_DIR / "decision_desk_assets_henri.json").write_text(out_json.read_text())
    (ASSETS / "decision_desk_shortlist_henri.json").write_text(json.dumps(bundle, indent=2))
    # Lightweight geo for shortlist bundle (wet features + Ida geometry for dry stubs)
    geo_features = []
    if out_geo.exists():
        geo = json.loads(out_geo.read_text())
        keep = set(seen)
        geo_features = [f for f in (geo.get("features") or []) if (f.get("properties") or {}).get("id") in keep]
    ida_geo_path = ASSETS / "decision_desk_assets.geojson"
    if dry_stubs and ida_geo_path.exists():
        ida_geo = json.loads(ida_geo_path.read_text())
        dry_ids = {a["id"] for a in dry_stubs}
        have = {(f.get("properties") or {}).get("id") for f in geo_features}
        for ft in ida_geo.get("features") or []:
            props = ft.get("properties") or {}
            aid = props.get("id")
            if aid in dry_ids and aid not in have and aid in by_id:
                geo_features.append(
                    {"type": "Feature", "properties": dict(by_id[aid]), "geometry": ft.get("geometry")}
                )
                have.add(aid)
    (ASSETS / "decision_desk_shortlist_henri.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": geo_features})
    )
    return {
        "assets_json": out_json.name,
        "assets_geojson": out_geo.name,
        "shortlist_json": "decision_desk_shortlist_henri.json",
        "shortlist_geojson": "decision_desk_shortlist_henri.geojson",
        "wet_total": payload["counts"]["wet_total"],
        "shortlist_present": [a["id"] for a in mapped],
        "shortlist_below_band": [a["id"] for a in dry_stubs],
        "shortlist_missing": [i for i in shortlist if i not in by_id],
        "top": [
            {
                "id": a["id"],
                "name": a["name"],
                "cm": a["max_depth_cm"],
                "band": a["band_label"],
                "lead_h": a["first_exceedance_lead_h"],
            }
            for a in payload["assets"][:5]
            if not a.get("henri_dry_stub")
        ],
    }


def build_henri_radar(cache: dict) -> dict:
    print("Building Henri soft-edge MRMS radar + susceptibility loop…")
    ASSETS.mkdir(parents=True, exist_ok=True)
    E2_DIR.mkdir(parents=True, exist_ok=True)
    SUSC_DIR.mkdir(parents=True, exist_ok=True)
    transform = _display_transform()
    fade = _load_land_fade(transform)

    factor_dir = PROCESSED_DIR / "susceptibility_factors"
    landscape = np.zeros(DISPLAY_SHAPE, dtype=np.float32)
    infra = np.zeros(DISPLAY_SHAPE, dtype=np.float32)
    for name, dst in (("factor_landscape.tif", landscape), ("factor_infra.tif", infra)):
        path = factor_dir / name
        if path.exists():
            _warp_to_display(path, dst, transform)
    imp_metro = PROCESSED_DIR / "drainage_capacity" / "impervious_fraction_metro.tif"
    if imp_metro.exists():
        imp = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        terrain = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        _warp_to_display(imp_metro, imp, transform)
        if (factor_dir / "factor_terrain.tif").exists():
            _warp_to_display(factor_dir / "factor_terrain.tif", terrain, transform)
        landscape = np.clip(
            0.55 * np.nan_to_num(terrain, nan=0.0) + 0.45 * np.nan_to_num(imp, nan=0.0),
            0,
            1,
        )

    dense = []
    for lead in cache["hours_ok"]:
        path = MRMS_DIR / f"mrms_qpe_metro_henri_1h_lead_{lead:02d}h.tif"
        field = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        _warp_to_display(path, field, transform)
        dense.append(
            {
                "lead_hours": float(lead),
                "valid_time": _valid_time(lead),
                "field": field,
                "native": True,
                "temporal_blend": False,
            }
        )

    vmax = max(
        (float(np.nanmax(f["field"])) for f in dense if np.isfinite(f["field"]).any()),
        default=1.0,
    )
    precip_frames, susc_frames = [], []
    for i, fr in enumerate(dense):
        display = fr["field"].astype(np.float32)
        lead = int(round(fr["lead_hours"]))
        stem = f"{PREFIX}precip_lead_{lead:02d}h"
        _write_tif_display(E2_DIR / f"{stem}.tif", display, transform)
        _write_png(ASSETS / f"{stem}.png", _rgba_precip(display, vmax=max(vmax, 5.0), fade=fade))
        pnorm = np.clip(np.nan_to_num(display, nan=0.0) / max(vmax, 1e-6), 0, 1)
        susc = combine_frame(landscape, infra, pnorm)
        susc = np.where(fade > 0.05, susc, np.nan)
        susc_stem = stem.replace("precip_", "susc_")
        _write_tif_display(SUSC_DIR / f"{susc_stem}.tif", susc, transform)
        _write_png(ASSETS / f"{susc_stem}.png", _rgba_susc(susc, fade=fade))
        precip_frames.append(
            {
                "index": i,
                "lead_hours": float(lead),
                "valid_time": fr["valid_time"],
                "png": f"{stem}.png",
                "tif": _rel(E2_DIR / f"{stem}.tif"),
                "mean_mm": float(np.nanmean(display)),
                "max_mm": float(np.nanmax(display)) if np.isfinite(display).any() else None,
                "native": True,
                "temporal_blend": False,
                "resolution_note": (
                    "~1 km MRMS Multi-Sensor QPE 01H Henri on metro DEM grid — soft land+edge alpha · native hourly"
                ),
            }
        )
        susc_frames.append(
            {
                "index": i,
                "lead_hours": float(lead),
                "valid_time": fr["valid_time"],
                "png": f"{susc_stem}.png",
                "tif": _rel(SUSC_DIR / f"{susc_stem}.tif"),
                "mean": float(np.nanmean(susc)) if np.isfinite(susc).any() else None,
                "formula": FORMULA,
            }
        )

    total = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
    _warp_to_display(cache["storm_total_tif"], total, transform)
    total_png = f"{PREFIX}precip_storm_total.png"
    _write_tif_display(E2_DIR / f"{PREFIX}precip_storm_total.tif", total, transform)
    _write_png(
        ASSETS / total_png,
        _rgba_precip(total, vmax=max(float(np.nanmax(total)), 10.0), fade=fade),
    )

    time_window = {
        "init_time_utc": INIT.strftime("%Y-%m-%dT%H:%M"),
        "first_valid_time_utc": precip_frames[0]["valid_time"] if precip_frames else None,
        "last_valid_time_utc": precip_frames[-1]["valid_time"] if precip_frames else None,
        "lead_hours_min": precip_frames[0]["lead_hours"] if precip_frames else None,
        "lead_hours_max": precip_frames[-1]["lead_hours"] if precip_frames else None,
        "native_leads_h": list(cache["hours_ok"]),
        "native_hourly": True,
        "loop_step_h": 1.0,
        "n_frames": len(precip_frames),
        "depth_cum_leads_h": list(CUM_LEADS),
        "note": (
            "Henri MRMS awareness loop covers +0h…+24h from 2021-08-21T18:00 UTC "
            "with native hourly MultiSensor QPE (research replay)."
        ),
    }
    leaflet = _leaflet_bounds()
    precip_meta = {
        "frames": precip_frames,
        "storm_total_png": total_png,
        "storm_total_max_mm": float(np.nanmax(total)) if np.isfinite(total).any() else None,
        "bounds": leaflet,
        "extent": PRIMARY_DATA_EXTENT,
        "soft_edge": True,
        "land_mask": True,
        "colorbar": {"cmap": PRECIP_CMAP, "units": "mm", "label": "MRMS QPE 1h (mm)"},
        "opacity_default": 0.72,
        "approx_resolution_km": 1.0,
        "loop_note": "Metro soft-edge MRMS Henri: native hourly MultiSensor QPE 0–24h",
        "time_window": time_window,
        "event_id": "henri-2021",
        "labeled": "Henri MRMS QPE research replay",
    }
    susc_meta = {
        "frames": susc_frames,
        "bounds": leaflet,
        "extent": PRIMARY_DATA_EXTENT,
        "soft_edge": True,
        "formula": FORMULA,
        "disclaimer": (
            "Henri screening index (weather evolves; landscape/infra mostly static). "
            "Not flood probability / not depth. Soft metro land+edge mask."
        ),
        "colorbar": {"cmap": SUSC_CMAP, "units": "index 0–1", "label": "Susceptibility (screening)"},
        "opacity_default": 0.55,
        "time_window": time_window,
        "event_id": "henri-2021",
    }
    (ASSETS / "henri_radar_meta.json").write_text(
        json.dumps(
            {
                "storm_path_id": STORM_PATH_ID,
                "n_frames": len(precip_frames),
                "time_window": time_window,
                "honesty": (
                    "Henri MRMS MultiSensor QPE radar loop — research replay, NOT NEXRAD tiles / NOT NWS."
                ),
            },
            indent=2,
        )
    )
    return {"precip": precip_meta, "susceptibility": susc_meta, "time_window": time_window}


def _rgba_depth(depth_m: np.ndarray, land: np.ndarray, vmax: float) -> np.ndarray:
    finite = np.isfinite(depth_m) & (depth_m >= MIN_DEPTH_M) & (land > 0.05)
    data = np.clip(np.where(np.isfinite(depth_m), depth_m, 0.0) / max(vmax, 1e-6), 0, 1)
    rgba = colormaps[DEPTH_CMAP](data, bytes=True)
    rgba[..., 3] = np.where(finite, np.minimum(220, 40 + (data * 180).astype(np.uint8)), 0)
    return rgba


def build_henri_depth_pngs(cache: dict) -> dict:
    print("Building Henri depth PNGs…")
    transform = _display_transform()
    fade = _load_land_fade(transform)
    leaflet = _leaflet_bounds()

    def warp_depth(path: Path) -> np.ndarray:
        out = np.full(DISPLAY_SHAPE, np.nan, dtype=np.float32)
        return _warp_to_display(path, out, transform)

    total = warp_depth(cache["depth_tif"])
    vmax = float(np.nanmax(total)) if np.isfinite(total).any() else 0.2
    vmax = max(vmax, 0.15)
    total_png = "depth_metro_mrms_qpe_henri_storm_total_m.png"
    _write_png(ASSETS / total_png, _rgba_depth(total, fade, vmax))

    cum_frames = []
    for lead, path in cache["lead_tifs"]:
        d = warp_depth(path)
        png = f"depth_metro_mrms_henri_cum_lead_{int(lead):02d}h_m.png"
        _write_png(ASSETS / png, _rgba_depth(d, fade, vmax))
        cum_frames.append(
            {
                "lead_hours": float(lead),
                "png": png,
                "tif": _rel(path),
                "evolves_with_timeline": True,
            }
        )

    inundation = {
        "product": "henri_metro_hand_depth",
        "primary": True,
        "role": "primary_research_depth",
        "extent": PRIMARY_DATA_EXTENT,
        "bounds": leaflet,
        "forcing": "spatial_mrms_qpe_henri_minus_drainage_capacity_proxy",
        "forcing_kind": "mrms_qpe_henri",
        "event_id": "henri-2021",
        "storm_total": {
            "png": total_png,
            "tif": _rel(cache["depth_tif"]),
            "max_depth_m": float(np.nanmax(total)) if np.isfinite(total).any() else None,
        },
        "cumulative_frames": cum_frames,
        "honesty": (
            "Henri HAND depth after drainage capacity proxy — research screening, "
            "NOT NWS / NOT street-truth / NOT DEP sewer."
        ),
    }
    (ASSETS / "depth_metro_mrms_qpe_henri_meta.json").write_text(json.dumps(inundation, indent=2))
    return inundation


def build_compare_strip(desk_meta: dict) -> dict:
    print("Building Ida↔Henri same-ID compare strip…")
    ida = json.loads((ASSETS / "decision_desk_assets.json").read_text())
    henri = json.loads((ASSETS / "decision_desk_assets_henri.json").read_text())
    ida_by = {a["id"]: a for a in ida.get("assets") or []}
    henri_by = {a["id"]: a for a in henri.get("assets") or []}
    shortlist = demo_shortlist_ids()
    rows = []
    for aid in shortlist:
        ia = ida_by.get(aid)
        ha = henri_by.get(aid)
        rows.append(
            {
                "id": aid,
                "name": (ia or ha or {}).get("name"),
                "ida_cm": None if not ia else ia.get("max_depth_cm"),
                "henri_cm": None if not ha else ha.get("max_depth_cm"),
                "ida_band": None if not ia else ia.get("band"),
                "henri_band": None if not ha else ha.get("band"),
                "ida_lead_h": None if not ia else ia.get("first_exceedance_lead_h"),
                "henri_lead_h": None if not ha else ha.get("first_exceedance_lead_h"),
                "present_in": (
                    "both"
                    if ia and ha
                    else ("ida_only" if ia else ("henri_only" if ha else "neither"))
                ),
            }
        )
    # Also include a few shared deep hits beyond shortlist for research browsing
    shared_ids = sorted(set(ida_by) & set(henri_by))
    extra = []
    for aid in shared_ids:
        if aid in shortlist:
            continue
        ia, ha = ida_by[aid], henri_by[aid]
        if float(ia.get("max_depth_cm") or 0) < 8 and float(ha.get("max_depth_cm") or 0) < 8:
            continue
        extra.append(
            {
                "id": aid,
                "name": ia.get("name") or ha.get("name"),
                "ida_cm": ia.get("max_depth_cm"),
                "henri_cm": ha.get("max_depth_cm"),
                "ida_band": ia.get("band"),
                "henri_band": ha.get("band"),
                "delta_cm": round(float(ia.get("max_depth_cm") or 0) - float(ha.get("max_depth_cm") or 0), 1),
            }
        )
    extra.sort(key=lambda r: -abs(float(r.get("delta_cm") or 0)))
    payload = {
        "product": "ida_henri_compare_strip",
        "honesty": (
            "Same official inventory IDs · research HAND depths — NOT peer-calibrated events · NOT NWS."
        ),
        "shortlist": rows,
        "shared_wet_sample": extra[:25],
        "n_shared_ids": len(shared_ids),
        "n_shortlist_both": sum(1 for r in rows if r["present_in"] == "both"),
        "desk": desk_meta,
    }
    out = ASSETS / "ida_henri_compare_strip.json"
    out.write_text(json.dumps(payload, indent=2))
    (OUTPUTS_DIR / "ida_henri_compare_strip.json").write_text(out.read_text())
    return payload


def patch_manifests(desk_meta: dict, radar: dict, inundation: dict, compare: dict) -> None:
    leaflet = _leaflet_bounds()
    henri_path = {
        "id": STORM_PATH_ID,
        "label": "MRMS QPE Henri (~1 km)",
        "scenario_kind": "henri_second_storm_hires_viz",
        "primary": False,
        "ida_primary_viz": False,
        "henri_event_viz": True,
        "event_id": "henri-2021",
        "source": "NOAA MRMS Multi-Sensor QPE — Tropical Storm Henri remnants 2021-08-21",
        "source_file": "data/processed/mrms_qpe_metro_henri",
        "honesty": (
            "Henri MRMS MultiSensor QPE research replay (~1 km) on soft-edge metro domain — "
            "NOT NEXRAD tiles; NOT an official NWS flood warning. Second-storm path; Ida remains default."
        ),
        "precip": radar["precip"],
        "susceptibility": radar["susceptibility"],
        "extent": PRIMARY_DATA_EXTENT,
    }
    second_storm = {
        "event_id": "henri-2021",
        "available": True,
        "parity": True,
        "parity_version": "henri_v1_official_inventory",
        "storm_path_id": STORM_PATH_ID,
        "meta": "second_storm_henri_meta.json",
        "radar_meta": "henri_radar_meta.json",
        "compare_strip": "ida_henri_compare_strip.json",
        "desk": desk_meta,
        "honesty": (
            "Henri Event switch swaps radar + official-inventory desk + shortlist — research only, "
            "NOT peer-calibrated to Ida talk-track depths."
        ),
    }
    henri_meta = {
        "event_id": "henri-2021",
        "available": True,
        "parity": True,
        "init_time_utc": INIT.isoformat(),
        "mrms_hours": radar["time_window"].get("native_leads_h"),
        "desk": desk_meta,
        "radar": {"n_frames": radar["precip"]["n_frames"] if "n_frames" in radar["precip"] else len(radar["precip"]["frames"])},
        "inundation": {
            "storm_total_png": inundation["storm_total"]["png"],
            "cum_leads_h": [f["lead_hours"] for f in inundation["cumulative_frames"]],
        },
        "compare_strip": compare,
        "honesty": second_storm["honesty"],
    }
    # Fix radar n_frames key
    henri_meta["radar"] = {"n_frames": len(radar["precip"]["frames"]), "storm_path_id": STORM_PATH_ID}
    (ASSETS / "second_storm_henri_meta.json").write_text(json.dumps(henri_meta, indent=2))
    (OUTPUTS_DIR / "second_storm_henri_meta.json").write_text(
        (ASSETS / "second_storm_henri_meta.json").read_text()
    )

    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        paths = list(m.get("storm_paths") or [])
        paths = [p for p in paths if p.get("id") != STORM_PATH_ID]
        # Keep Ida primary first; insert Henri after Ida MRMS
        insert_at = 1
        for i, p in enumerate(paths):
            if p.get("id") == "mrms_qpe_ida" or p.get("ida_primary_viz"):
                insert_at = i + 1
                break
        paths.insert(insert_at, henri_path)
        m["storm_paths"] = paths
        m["second_storm"] = second_storm
        m["ida_henri_compare"] = {
            "json": "ida_henri_compare_strip.json",
            "honesty": compare.get("honesty"),
            "n_shortlist_both": compare.get("n_shortlist_both"),
        }
        desk = m.setdefault("asset_decision_desk", {})
        desk["events"] = {
            "ida-2021": {
                "assets_json": "decision_desk_assets.json",
                "assets_geojson": "decision_desk_assets.geojson",
                "shortlist_json": desk.get("shortlist_json") or "decision_desk_shortlist.json",
                "shortlist_geojson": desk.get("shortlist_geojson") or "decision_desk_shortlist.geojson",
                "storm_path_id": "mrms_qpe_ida",
            },
            "henri-2021": {
                "assets_json": desk_meta["assets_json"],
                "assets_geojson": desk_meta["assets_geojson"],
                "shortlist_json": desk_meta["shortlist_json"],
                "shortlist_geojson": desk_meta["shortlist_geojson"],
                "storm_path_id": STORM_PATH_ID,
            },
        }
        desk["henri_parity"] = True
        desk["compare_strip_json"] = "ida_henri_compare_strip.json"
        inv = m.get("inundation") or {}
        by_path = dict(inv.get("by_path") or {})
        by_path[STORM_PATH_ID] = inundation
        # Preserve Ida default inundation object; attach Henri under by_path
        if "storm_total" in inv and "cumulative_frames" in inv:
            by_path.setdefault("mrms_qpe_ida", {
                "storm_total": inv.get("storm_total"),
                "cumulative_frames": inv.get("cumulative_frames"),
                "bounds": inv.get("bounds") or leaflet,
                "extent": inv.get("extent") or PRIMARY_DATA_EXTENT,
            })
        inv["by_path"] = by_path
        m["inundation"] = inv
        m["inundation_henri"] = inundation
        mp.write_text(json.dumps(m, indent=2))


def regenerate_html() -> Path | None:
    from product_map_html import write_product_html

    manifest = json.loads((ASSETS / "product_manifest.json").read_text())
    pluvial = (
        json.loads((ASSETS / "pluvial_meta.json").read_text())
        if (ASSETS / "pluvial_meta.json").exists()
        else {}
    )
    validation = (
        json.loads((ASSETS / "validation_product.json").read_text())
        if (ASSETS / "validation_product.json").exists()
        else {}
    )
    return write_product_html(manifest, pluvial, validation)


def main() -> dict:
    cache = require_cached_inputs()
    desk_meta = rebuild_henri_desk(cache)
    radar = build_henri_radar(cache)
    inundation = build_henri_depth_pngs(cache)
    compare = build_compare_strip(desk_meta)
    patch_manifests(desk_meta, radar, inundation, compare)
    html = regenerate_html()
    summary = {
        "parity": True,
        "desk": desk_meta,
        "radar_frames": len(radar["precip"]["frames"]),
        "depth_cum_frames": len(inundation["cumulative_frames"]),
        "compare_shortlist_both": compare.get("n_shortlist_both"),
        "html": str(html) if html else None,
        "honesty": "Henri Event switch ready — research only.",
    }
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
