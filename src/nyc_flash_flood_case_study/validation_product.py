"""Automated Earth2 vs MRMS vs 311 validation summary (exploratory, not skill certification)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from .config import FIGURES_DIR, IMPACT_DATASETS, OUTPUTS_DIR, PROJECT_ROOT


def _sample_raster(path: Path, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    values = np.full(len(lons), np.nan, dtype=np.float64)
    if not path.exists():
        return values
    with rasterio.open(path) as src:
        for i, (lon, lat) in enumerate(zip(lons, lats)):
            val = next(src.sample([(float(lon), float(lat))]))[0]
            if src.nodata is not None and np.isclose(val, src.nodata):
                continue
            if np.isfinite(val):
                values[i] = float(val)
    return values


def _domain_stats(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
    vals = data.compressed()
    if vals.size == 0:
        return {"exists": True, "n": 0}
    return {
        "exists": True,
        "n": int(vals.size),
        "mean_mm": float(np.mean(vals)),
        "max_mm": float(np.max(vals)),
        "p90_mm": float(np.percentile(vals, 90)),
    }


def build_validation_product(
    earth2_storm_tif: Path,
    mrms_storm_tif: Path | None = None,
    assets_dir: Path | None = None,
) -> dict:
    """Write JSON (+ optional assets copy) summarizing Earth2 / MRMS / 311 overlap."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = assets_dir or (FIGURES_DIR / "product_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)

    e2 = _domain_stats(earth2_storm_tif)
    mrms_path = mrms_storm_tif or (PROJECT_ROOT / "data" / "processed" / "mrms_qpe" / "mrms_qpe_storm_total.tif")
    mrms = _domain_stats(mrms_path)

    report: dict = {
        "status": "exploratory_validation_product",
        "valid_operational_skill": False,
        "earth2_storm_total": e2,
        "mrms_qpe_storm_total": mrms,
        "comparison": {},
        "reports_311": {},
        "limitations": [
            "Earth2 native grid is ~0.25°; bilinear display resampling is not physical downscaling.",
            "MRMS QPE and Earth2 grids differ; domain stats are not a formal verification scorecard.",
            "311 flood-related complaints are not surveyed flood extents or depths.",
            "No verified non-flood locations → no ROC/AUC/calibration claims.",
            "This panel never issues flood warnings or emergency guidance.",
        ],
    }

    if e2.get("exists") and mrms.get("exists") and e2.get("n", 0) and mrms.get("n", 0):
        report["comparison"] = {
            "max_mm_earth2_minus_mrms": float(e2["max_mm"] - mrms["max_mm"]),
            "mean_mm_earth2_minus_mrms": float(e2["mean_mm"] - mrms["mean_mm"]),
            "earth2_underestimates_domain_max": bool(e2["max_mm"] < mrms["max_mm"]),
        }

    # Prefer app impacts path; fall back to legacy extract
    reports_csv = IMPACT_DATASETS["nyc_311"]
    if not reports_csv.exists():
        alt = PROJECT_ROOT / "legacy_projects_data" / "raw" / "impacts" / "nyc_311_flooding.csv"
        reports_csv = alt if alt.exists() else reports_csv

    if reports_csv.exists() and earth2_storm_tif.exists():
        df = pd.read_csv(reports_csv).dropna(subset=["lon", "lat"])
        e2_at = _sample_raster(earth2_storm_tif, df["lon"].to_numpy(), df["lat"].to_numpy())
        mrms_at = _sample_raster(mrms_path, df["lon"].to_numpy(), df["lat"].to_numpy()) if mrms_path.exists() else np.full(len(df), np.nan)
        valid_e2 = np.isfinite(e2_at)
        report["reports_311"] = {
            "n_reports": int(len(df)),
            "n_with_earth2_sample": int(valid_e2.sum()),
            "median_earth2_mm_at_reports": float(np.nanmedian(e2_at)) if valid_e2.any() else None,
            "fraction_reports_above_earth2_p75": None,
            "median_mrms_mm_at_reports": float(np.nanmedian(mrms_at)) if np.isfinite(mrms_at).any() else None,
        }
        if e2.get("exists") and e2.get("n", 0):
            with rasterio.open(earth2_storm_tif) as src:
                grid = src.read(1, masked=True).compressed()
            if grid.size:
                p75 = float(np.percentile(grid, 75))
                report["reports_311"]["earth2_domain_p75_mm"] = p75
                report["reports_311"]["fraction_reports_above_earth2_p75"] = (
                    float(np.nanmean(e2_at >= p75)) if valid_e2.any() else None
                )

    out_json = OUTPUTS_DIR / "validation_product.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n")
    (assets_dir / "validation_product.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
