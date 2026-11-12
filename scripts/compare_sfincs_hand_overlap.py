#!/usr/bin/env python3
"""Phase E helper — overlap metrics SFINCS Queens vs primary HAND on shared AOI.

Wet/dry disagreement flags only — never blends depths into a fake peer field.
Also records whether SFINCS forcing used the shared drainage-capacity proxy sink.
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

from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402
from nyc_flash_flood_case_study.extents import EXTENTS  # noqa: E402

INUN = PROCESSED_DIR / "inundation"
ASSETS = FIGURES_DIR / "product_assets"
SFINCS = INUN / "depth_sfincs_queens_ida_m.tif"
HAND = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
WET_M = 0.005


def main() -> dict:
    if not SFINCS.exists():
        raise FileNotFoundError(f"Missing SFINCS depth: {SFINCS}")
    if not HAND.exists():
        raise FileNotFoundError(f"Missing primary HAND depth: {HAND}")

    with rasterio.open(SFINCS) as sf:
        sf_depth = sf.read(1).astype(np.float32)
        if sf.nodata is not None:
            sf_depth = np.where(sf_depth == sf.nodata, np.nan, sf_depth)
        transform = sf.transform
        crs = sf.crs
        shape = sf_depth.shape

    hand_on_sf = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(HAND) as hd:
        src = hd.read(1).astype(np.float32)
        if hd.nodata is not None:
            src = np.where(src == hd.nodata, np.nan, src)
        reproject(
            source=src,
            destination=hand_on_sf,
            src_transform=hd.transform,
            src_crs=hd.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )

    # Shared AOI = south_queens bbox ∩ finite cells
    b = EXTENTS["south_queens"]["bounds"]
    rows, cols = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    in_aoi = (
        (xs >= b["xmin"])
        & (xs <= b["xmax"])
        & (ys >= b["ymin"])
        & (ys <= b["ymax"])
        & np.isfinite(sf_depth)
        & np.isfinite(hand_on_sf)
    )

    sf_w = (sf_depth >= WET_M) & in_aoi
    hd_w = (hand_on_sf >= WET_M) & in_aoi
    both = sf_w & hd_w
    sf_only = sf_w & ~hd_w
    hd_only = hd_w & ~sf_w
    n_aoi = int(in_aoi.sum())

    ratio_mean = None
    if both.any():
        ratio_mean = float(np.mean(sf_depth[both] / np.maximum(hand_on_sf[both], 1e-6)))

    build_meta = {}
    bmp = OUTPUTS_DIR / "sfincs_queens_ida" / "build_meta.json"
    if bmp.exists():
        build_meta = json.loads(bmp.read_text())
    precip_meta = build_meta.get("precip_netcdf") or {}
    drainage = precip_meta.get("drainage_capacity_proxy") or {}

    sfincs_asset_meta = {}
    amp = ASSETS / "depth_sfincs_queens_ida_meta.json"
    if amp.exists():
        sfincs_asset_meta = json.loads(amp.read_text())

    report = {
        "phase": "E",
        "product": "sfincs_hand_overlap",
        "extent": "south_queens",
        "wet_threshold_m": WET_M,
        "n_aoi_cells": n_aoi,
        "wet_dry": {
            "sfincs_wet": int(sf_w.sum()),
            "hand_wet": int(hd_w.sum()),
            "both_wet": int(both.sum()),
            "sfincs_only": int(sf_only.sum()),
            "hand_only": int(hd_only.sum()),
            "agreement_fraction_on_union": (
                float(both.sum() / (sf_w | hd_w).sum()) if (sf_w | hd_w).any() else None
            ),
        },
        "magnitude_on_both_wet": {
            "sfincs_mean_m": float(np.mean(sf_depth[both])) if both.any() else None,
            "hand_mean_m": float(np.mean(hand_on_sf[both])) if both.any() else None,
            "sfincs_over_hand_mean_ratio": ratio_mean,
            "note": "Non-peer magnitudes — report ratio, do not blend.",
        },
        "shared_sink": {
            "applied_on_sfincs_forcing": bool(drainage.get("applied")),
            "engine": drainage.get("engine"),
            "drain_points_n": drainage.get("drain_points_n"),
            "note": (
                "Same drainage_capacity_proxy_v1 language as HAND excess precip when "
                "SFINCS rebuild applies excess-rate forcing."
            ),
        },
        "sfincs_meta": {
            "max_m": sfincs_asset_meta.get("max_m"),
            "forcing": sfincs_asset_meta.get("forcing"),
            "role": "alternate_hydro_track",
            "primary": False,
        },
        "product_default_unchanged": True,
        "honesty": (
            "SFINCS Queens remains Advanced/alt. Overlap is wet/dry + residual gap — "
            "never a peer depth toggle with metro HAND."
        ),
        "official_nws": False,
        "decision_grade": False,
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (ASSETS / "sfincs_hand_overlap.json").write_text(json.dumps(report, indent=2))
    (OUTPUTS_DIR / "sfincs_hand_overlap.json").write_text(json.dumps(report, indent=2))
    (INUN / "sfincs_hand_overlap.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("wet_dry", "magnitude_on_both_wet", "shared_sink")}, indent=2))
    return report


if __name__ == "__main__":
    main()
