#!/usr/bin/env python3
"""P2.6 — True nested SFINCS boundary exchange + non-peer HAND calib (Advanced only).

Upgrades hard nest paste to a feathered research exchange:
  - Nest interior kept
  - Coarse exterior kept
  - Soft transition ring around nest footprint (boundary exchange)
  - Diagnostics: boundary residual coarse↔nest, overlap vs HAND (non-peer)

HAND remains primary. Never blends SFINCS into HAND ranks.
NOT SWMM / NOT DEP / NOT NWS.
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
from rasterio.warp import reproject
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.inundation.sfincs_nested import feathered_nest_exchange  # noqa: E402
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402
from nyc_flash_flood_case_study.extents import EXTENTS  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
FEATHER_PX = 8
ENGINE_ID = "sfincs_metro_nested_exchange_v1"


def _warp(src_path: Path, shape, transform, crs) -> np.ndarray:
    out = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
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
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(data.astype(np.float32), 1)


def _write_png(path: Path, depth: np.ndarray) -> None:
    finite = np.isfinite(depth) & (depth > 0.005)
    vmax = float(np.nanpercentile(depth[finite], 98)) if finite.any() else 0.5
    vmax = max(vmax, 0.05)
    norm = np.clip(np.nan_to_num(depth, nan=0.0) / vmax, 0, 1)
    rgba = (colormaps["Blues"](norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(finite, np.clip(80 + norm * 175, 0, 255).astype(np.uint8), 0)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def hand_overlap_calib(composite: np.ndarray, hand: np.ndarray, nest_mask: np.ndarray) -> dict:
    """Non-peer overlap stats — never used to rescale HAND."""
    mask = nest_mask & np.isfinite(composite) & np.isfinite(hand)
    if not mask.any():
        return {"n": 0, "note": "no overlap cells"}
    c = composite[mask]
    h = hand[mask]
    return {
        "n": int(mask.sum()),
        "hand_mean_m": float(np.mean(h)),
        "sfincs_mean_m": float(np.mean(c)),
        "rmse_m": float(np.sqrt(np.mean((c - h) ** 2))),
        "bias_sfincs_minus_hand_m": float(np.mean(c - h)),
        "non_peer": True,
        "note": (
            "Overlap diagnostics only — magnitudes not peer; do NOT rescale HAND to SFINCS "
            "or blend engines into primary ranks."
        ),
    }


def main() -> dict:
    coarse_tif = INUN / "depth_sfincs_metro_ida_m.tif"
    nest_tif = INUN / "depth_sfincs_queens_ida_m.tif"
    hand_tif = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    for p in (coarse_tif, nest_tif):
        if not p.exists():
            raise SystemExit(f"missing {p} — run build_and_run_sfincs_metro_nested.py first")

    with rasterio.open(coarse_tif) as cs:
        coarse = cs.read(1).astype(np.float32)
        transform, crs = cs.transform, cs.crs
        shape = coarse.shape
        if cs.nodata is not None:
            coarse = np.where(coarse == cs.nodata, np.nan, coarse)

    nest = _warp(nest_tif, shape, transform, crs)
    hand = _warp(hand_tif, shape, transform, crs) if hand_tif.exists() else np.full(shape, np.nan)

    composite, exch = feathered_nest_exchange(coarse, nest, feather_px=FEATHER_PX)
    nest_mask = np.isfinite(nest)
    calib = hand_overlap_calib(composite, hand, nest_mask)

    out_tif = INUN / "depth_sfincs_metro_nested_ida_m.tif"
    out_png = ASSETS / "depth_sfincs_metro_nested_ida_m.png"
    out_meta = ASSETS / "depth_sfincs_metro_nested_ida_meta.json"
    exch_json = ASSETS / "sfincs_nest_exchange.json"

    _write_tif(out_tif, composite, transform, crs)
    _write_png(out_png, composite)

    b = EXTENTS["metro"]["bounds"]
    leaflet = [[b["ymin"], b["xmin"]], [b["ymax"], b["xmax"]]]
    meta = {
        "engine": ENGINE_ID,
        "engine_label": "SFINCS metro nested + feathered boundary exchange — Advanced research only",
        "png": out_png.name,
        "tif": str(out_tif),
        "coarse_tif": str(coarse_tif),
        "nest_tif": str(nest_tif),
        "max_m": float(np.nanmax(composite)) if np.isfinite(composite).any() else None,
        "wet_fraction": float(np.mean(np.isfinite(composite) & (composite > 0.005))),
        "role": "advanced_research_hydro",
        "primary": False,
        "not_swmm": True,
        "official_nws": False,
        "decision_grade": False,
        "never_blend_into_hand": True,
        "exchange": exch,
        "hand_overlap_calib_non_peer": calib,
        "bounds": leaflet,
        "honesty": (
            "Feathered nest↔coarse boundary exchange for Advanced SFINCS visualization. "
            "HAND stays primary; engines are non-peer; NOT SWMM / NOT DEP / NOT NWS."
        ),
    }
    out_meta.write_text(json.dumps(meta, indent=2))
    exch_payload = {
        "product": "sfincs_nest_exchange",
        "engine": ENGINE_ID,
        "exchange": exch,
        "hand_overlap_calib_non_peer": calib,
        "honesty": meta["honesty"],
        "official_nws": False,
        "decision_grade": False,
        "not_swmm": True,
        "primary_remains": "pysheds_hand_bathtub_v2",
    }
    exch_json.write_text(json.dumps(exch_payload, indent=2))
    (OUTPUTS_DIR / "sfincs_nest_exchange.json").write_text(exch_json.read_text())

    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["inundation_sfincs_nested"] = {
            "png": out_png.name,
            "meta": out_meta.name,
            "exchange_json": exch_json.name,
            "engine": ENGINE_ID,
            "extent": "metro",
            "bounds": leaflet,
            "role": "advanced_research_hydro",
            "primary": False,
            "not_swmm": True,
            "never_blend_into_hand": True,
            "honesty": meta["honesty"],
        }
        m["sfincs_nest_exchange"] = {
            "json": exch_json.name,
            "available": True,
            "mode": exch.get("mode"),
            "hand_rmse_m": (calib or {}).get("rmse_m"),
            "honesty": meta["honesty"],
        }
        mp.write_text(json.dumps(m, indent=2))

    try:
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
        write_product_html(manifest, pluvial, validation)
    except Exception as exc:  # noqa: BLE001
        print(f"html regen skipped: {exc}")

    summary = {
        "engine": ENGINE_ID,
        "exchange_mode": exch.get("mode"),
        "boundary_rmse_m": (exch.get("boundary_residual_m") or {}).get("rmse"),
        "hand_overlap_rmse_m": calib.get("rmse_m"),
        "max_m": meta["max_m"],
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
