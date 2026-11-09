#!/usr/bin/env python3
"""Validate included product layers: Earth2, MRMS, 311, pluvial, FEMA, NWM, drainage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.validation_product import build_validation_product

ASSETS = FIGURES_DIR / "product_assets"
OUT = PROJECT_ROOT / "outputs" / "full_validation_report.json"


def _check_raster(path: Path, expect_land_mask: bool = False) -> dict:
    if not path.exists():
        return {"ok": False, "error": "missing", "path": str(path)}
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        finite = np.ma.compressed(data)
        info = {
            "ok": True,
            "path": str(path),
            "crs": str(src.crs),
            "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
            "shape": [src.height, src.width],
            "finite_fraction": float((~data.mask).mean()) if np.ma.is_masked(data) else 1.0,
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
        }
        # Water-mask sanity: if land mask exists, water cells should be nodata-ish on precip/pluvial
        land_path = PROCESSED_DIR / "land_mask_citywide.tif"
        if expect_land_mask and land_path.exists():
            with rasterio.open(land_path) as land_src:
                from rasterio.warp import reproject
                from rasterio.enums import Resampling

                land = np.zeros((src.height, src.width), dtype=np.uint8)
                reproject(
                    source=rasterio.band(land_src, 1),
                    destination=land,
                    src_transform=land_src.transform,
                    src_crs=land_src.crs,
                    dst_transform=src.transform,
                    dst_crs=src.crs,
                    resampling=Resampling.nearest,
                )
            water = land == 0
            if water.any():
                water_vals = data[water]
                # masked array: count unmasked finite on water
                if np.ma.is_masked(data):
                    leak = float((~water_vals.mask).mean())
                else:
                    leak = float(np.isfinite(water_vals).mean())
                info["water_finite_leak_fraction"] = leak
                info["water_masked_ok"] = leak < 0.05
                if leak >= 0.05:
                    info["ok"] = False
                    info["error"] = f"water_leak={leak:.3f}"
        return info


def _check_geojson(path: Path, min_features: int = 1) -> dict:
    if not path.exists():
        return {"ok": False, "error": "missing", "path": str(path)}
    data = json.loads(path.read_text())
    n = len(data.get("features", []))
    return {
        "ok": n >= min_features,
        "path": str(path),
        "n_features": n,
        "error": None if n >= min_features else "too_few_features",
    }


def main() -> None:
    e2 = PROCESSED_DIR / "earth2_precip" / "precip_storm_total.tif"
    mrms = PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif"
    product = build_validation_product(e2, mrms if mrms.exists() else None, ASSETS)

    checks = {
        "earth2_storm_total": _check_raster(e2, expect_land_mask=True),
        "earth2_lead_12h": _check_raster(PROCESSED_DIR / "earth2_precip" / "precip_lead_12h.tif", True),
        "mrms_storm_total": _check_raster(mrms, expect_land_mask=True),
        "pluvial_citywide": _check_raster(PROCESSED_DIR / "pluvial" / "pluvial_screening_citywide.tif", True),
        "land_mask_citywide": _check_raster(PROCESSED_DIR / "land_mask_citywide.tif"),
        "nlcd_citywide": _check_raster(PROJECT_ROOT / "data" / "raw" / "landcover" / "nlcd_2021_impervious_citywide.tif"),
        "fema_sfha": _check_geojson(ASSETS / "fema_nfhl.geojson", 10),
        "nwm_high_flow": _check_geojson(ASSETS / "nwm_high_flow.geojson", 1),
        "nwm_gauges": _check_geojson(ASSETS / "nwm_ahps_gauges.geojson", 1),
        "drainage_nodes": _check_geojson(ASSETS / "drainage_nodes.geojson", 10),
        "drainage_conduits": _check_geojson(ASSETS / "drainage_conduits.geojson", 10),
        "reports_311": _check_geojson(ASSETS / "observed_311.geojson", 10),
        "roads": _check_geojson(ASSETS / "roads.geojson", 10),
    }

    failures = {k: v for k, v in checks.items() if not v.get("ok")}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not failures else "fail",
        "n_checks": len(checks),
        "n_failures": len(failures),
        "failures": failures,
        "checks": checks,
        "earth2_vs_mrms_vs_311": product,
        "notes": [
            "Earth2 is coarse ~0.25°; domain stats vs MRMS are exploratory, not certified skill.",
            "Land-mask checks require scripts/apply_land_mask.py to have been run.",
            "Synthetic drainage is demo-only and is not a calibrated sewer model.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    (ASSETS / "full_validation_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"status": report["status"], "n_failures": report["n_failures"], "failures": list(failures)}, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
