"""Return-period placeholders from MRMS / ERA5 (hooks if not fetchable).

Research only — NOT official frequency analysis / NOT NWS.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


# Placeholder RP table: map storm-total precip (mm) classes to illustrative RPs.
# Explicitly unlabeled as unofficial / not calibrated for NYC.
PLACEHOLDER_RP_FROM_PRECIP_MM = [
    {"min_mm": 0, "max_mm": 25, "rp_years": 1, "label": "~1-yr class (placeholder)"},
    {"min_mm": 25, "max_mm": 50, "rp_years": 2, "label": "~2-yr class (placeholder)"},
    {"min_mm": 50, "max_mm": 75, "rp_years": 5, "label": "~5-yr class (placeholder)"},
    {"min_mm": 75, "max_mm": 100, "rp_years": 10, "label": "~10-yr class (placeholder)"},
    {"min_mm": 100, "max_mm": 150, "rp_years": 25, "label": "~25-yr class (placeholder)"},
    {"min_mm": 150, "max_mm": 200, "rp_years": 50, "label": "~50-yr class (placeholder)"},
    {"min_mm": 200, "max_mm": None, "rp_years": 100, "label": "~100-yr+ class (placeholder)"},
]


def _rp_for_mm(mm: float) -> dict[str, Any]:
    for row in PLACEHOLDER_RP_FROM_PRECIP_MM:
        hi = row["max_mm"]
        if mm >= row["min_mm"] and (hi is None or mm < hi):
            return dict(row)
    return dict(PLACEHOLDER_RP_FROM_PRECIP_MM[-1])


def _storm_total_mm_from_tif(path: Path) -> float | None:
    try:
        import rasterio
    except ImportError:
        return None
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        arr = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            arr = np.where(arr == ds.nodata, np.nan, arr)
        if not np.isfinite(arr).any():
            return None
        # Prefer high percentile as “event magnitude” proxy for placeholder RP
        return float(np.nanpercentile(arr, 99))


def try_fetch_era5_stub() -> dict[str, Any]:
    """ERA5 is not fetched in-CI; return hook metadata only."""
    return {
        "status": "hook",
        "source": "era5",
        "fetched": False,
        "reason": "CDS credentials / download not configured in this environment",
        "fetch_hint": "cdsapi retrieve reanalysis-era5-single-levels variable=total_precipitation for NYC bbox",
    }


def build_rp_placeholders(project_root: Path, assets_dir: Path) -> dict[str, Any]:
    mrms = project_root / "data" / "processed" / "mrms_qpe" / "mrms_qpe_storm_total.tif"
    mrms_alt = project_root / "data" / "processed" / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif"
    e2 = project_root / "data" / "processed" / "earth2_precip" / "precip_storm_total.tif"

    scenarios = []
    for sid, path, label in (
        ("mrms_qpe_ida", mrms_alt if mrms_alt.exists() else mrms, "MRMS QPE Ida storm total"),
        ("earth2_open", e2, "Earth2 open scenario storm total"),
    ):
        mm = _storm_total_mm_from_tif(path)
        entry: dict[str, Any] = {
            "id": sid,
            "label": label,
            "path": str(path) if path.exists() else None,
            "p99_precip_mm": mm,
            "status": "available" if mm is not None else "missing",
        }
        if mm is not None:
            entry["return_period_placeholder"] = _rp_for_mm(mm)
        scenarios.append(entry)

    era5 = try_fetch_era5_stub()
    out = {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": (
            "Placeholder RP classes from event p99 precip (mm) lookup table. "
            "NOT calibrated IDF / NOT USGS / NOT NWS frequency analysis."
        ),
        "lookup_table": PLACEHOLDER_RP_FROM_PRECIP_MM,
        "scenarios": scenarios,
        "era5": era5,
        "honesty": (
            "Return-period values are research placeholders for UI/scenario cards. "
            "ERA5 remains a hook until CDS fetch is configured."
        ),
    }
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "risk_return_period_placeholders.json").write_text(json.dumps(out, indent=2))
    return out
