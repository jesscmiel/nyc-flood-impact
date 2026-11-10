"""Hazard catalog hooks — MRMS / ERA5 / GFS (open stack; no Enterprise/HENS).

Provides a machine-readable catalog of available and planned hazard forcings.
Fetch helpers are stubs that record how to pull data; they do not require
Earth2Studio Enterprise.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

HazardKind = Literal["mrms_qpe", "era5", "gfs", "earth2_open", "other"]


@dataclass
class HazardSource:
    id: str
    kind: HazardKind
    label: str
    status: Literal["available", "hook", "blocked"]
    description: str
    variables: list[str] = field(default_factory=list)
    approx_resolution: str | None = None
    access: str | None = None
    local_paths: list[str] = field(default_factory=list)
    fetch_hint: str | None = None
    case_study_event: str | None = None


def default_catalog(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    mrms_dir = root / "data" / "processed" / "mrms_qpe"
    e2_dir = root / "data" / "processed" / "earth2_precip"
    mrms_paths = sorted(str(p.relative_to(root)) for p in mrms_dir.glob("*.tif")) if mrms_dir.exists() else []
    e2_mrms = sorted(str(p.relative_to(root)) for p in e2_dir.glob("mrms_qpe_ida*.tif")) if e2_dir.exists() else []

    sources = [
        HazardSource(
            id="mrms_qpe_ida",
            kind="mrms_qpe",
            label="NOAA MRMS Multi-Sensor QPE (Ida case study)",
            status="available",
            description="Radar+gauge QPE (~1 km) for 2021-09-01 Ida remnants over NYC metro.",
            variables=["precip_mm"],
            approx_resolution="~1 km",
            access="Local processed GeoTIFFs (case-study fixture)",
            local_paths=mrms_paths + e2_mrms,
            fetch_hint="Re-export via scripts that ingest MRMS MultiSensor_QPE; no Enterprise required.",
            case_study_event="ida-2021",
        ),
        HazardSource(
            id="era5_precip_hook",
            kind="era5",
            label="ERA5 total precipitation (hook)",
            status="hook",
            description="CDS/ERA5 hourly or daily precip for climatology / analogs. Not downloaded in this MVP.",
            variables=["tp"],
            approx_resolution="0.25°",
            access="Copernicus CDS API (open)",
            local_paths=[],
            fetch_hint=(
                "cdsapi retrieve reanalysis-era5-single-levels "
                "variable=total_precipitation area=NYC bbox; write netCDF → GeoTIFF."
            ),
        ),
        HazardSource(
            id="gfs_precip_hook",
            kind="gfs",
            label="GFS precipitation (hook)",
            status="hook",
            description="NCEP GFS forecast precip APCP for scenario / ops-style forcing. Not downloaded in this MVP.",
            variables=["tp", "apcp"],
            approx_resolution="~0.25°",
            access="NOMADS / AWS open data",
            local_paths=[],
            fetch_hint="Herbie or earth2studio data sources (open) → APCP; clip to metro bbox.",
        ),
        HazardSource(
            id="earth2_open_scenario",
            kind="earth2_open",
            label="Open Earth2-class AI precip scenario",
            status="available",
            description="Labeled AI scenario track from open Earth2Studio-class outputs (not Enterprise/HENS).",
            variables=["precip_mm"],
            approx_resolution="~0.25°",
            access="Local processed GeoTIFFs",
            local_paths=(
                sorted(str(p.relative_to(root)) for p in e2_dir.glob("precip_*.tif")) if e2_dir.exists() else []
            ),
            fetch_hint="Optional open FCN/PrecipitationAFNO when env installs; never claim NEXRAD.",
            case_study_event="ida-2021",
        ),
    ]

    return {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region_default": "nyc_metro_citywide",
        "bbox_default": {"xmin": -74.28, "ymin": 40.48, "xmax": -73.68, "ymax": 40.93},
        "sources": [asdict(s) for s in sources],
        "honesty": (
            "Hazard catalog lists available fixtures and open-data hooks. "
            "ERA5/GFS entries are hooks only until fetched. NOT official NWS guidance."
        ),
    }


def write_catalog(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    cat = default_catalog(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cat, indent=2))
    return cat


def fetch_stub(source_id: str) -> dict[str, Any]:
    """Return a non-fetching stub response for ERA5/GFS hooks."""
    cat = default_catalog()
    match = next((s for s in cat["sources"] if s["id"] == source_id), None)
    if not match:
        return {"ok": False, "error": f"unknown source {source_id}"}
    if match["status"] == "available":
        return {
            "ok": True,
            "source_id": source_id,
            "action": "use_local_paths",
            "paths": match.get("local_paths") or [],
        }
    return {
        "ok": False,
        "source_id": source_id,
        "action": "hook_only",
        "fetch_hint": match.get("fetch_hint"),
        "message": "Open-data hook registered; run an offline fetch job to materialize rasters.",
    }
