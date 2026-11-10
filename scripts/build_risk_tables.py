#!/usr/bin/env python3
"""Build depth×asset risk tables + borough pysheds spike; record SFINCS/LISFLOOD blockers.

Research flood-risk MVP — no Enterprise / HENS. NOT official NWS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.inundation.engine_spike import try_build_sfincs_schema, write_spike_report
from flood_risk.inundation.pysheds_borough import run_borough_spike
from flood_risk.risk.depth_asset_tables import summarize_assets
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

ASSETS = FIGURES_DIR / "product_assets"


def _ensure_facilities() -> Path:
    """Curated critical-facility demo points (research exposure stub)."""
    out = ASSETS / "critical_facilities.geojson"
    # Approximate public facilities across NYC metro for demo intersects
    pts = [
        ("NYC Health + Hospitals / Elmhurst", "hospital", -73.8865, 40.7389),
        ("Jamaica Hospital Medical Center", "hospital", -73.8057, 40.7005),
        ("Queens Hospital Center", "hospital", -73.8250, 40.7170),
        ("FDNY Engine 275", "fire", -73.8600, 40.7000),
        ("FDNY Engine 303", "fire", -73.7900, 40.7100),
        ("NYPD 103rd Precinct", "police", -73.8000, 40.6900),
        ("NYPD 105th Precinct", "police", -73.7400, 40.6700),
        ("Citi Field", "venue", -73.8458, 40.7571),
        ("JFK Terminal 4 area", "transport", -73.7820, 40.6440),
        ("LIRR Jamaica Station", "transport", -73.8077, 40.6995),
        ("Brooklyn Hospital Center", "hospital", -73.9700, 40.6900),
        ("NYU Langone Brooklyn", "hospital", -74.0000, 40.6500),
        ("Staten Island University Hospital", "hospital", -74.1000, 40.5850),
        ("Lincoln Medical Center", "hospital", -73.9240, 40.8160),
        ("Harlem Hospital", "hospital", -73.9400, 40.8140),
    ]
    feats = [
        {
            "type": "Feature",
            "properties": {"name": n, "facility_type": t, "source": "demo_stub"},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        }
        for n, t, lon, lat in pts
    ]
    gj = {
        "type": "FeatureCollection",
        "features": feats,
        "properties": {
            "note": "Demo critical facilities for research risk tables — not an authoritative inventory.",
            "official": False,
        },
    }
    out.write_text(json.dumps(gj))
    return out


def main() -> None:
    bounds = EXTENTS["south_queens"]["bounds"]
    dem = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
    rain = PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif"
    if not rain.exists():
        rain = PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif"

    # 1) Engine spike / blocker report
    bbox = (bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"])
    schema = try_build_sfincs_schema(OUTPUTS_DIR / "sfincs_spike_queens", bbox)
    spike = write_spike_report(
        OUTPUTS_DIR / "inundation_engine_spike.json",
        {"sfincs_schema": schema, "borough": "south_queens", "forcing": "mrms_qpe_ida"},
    )
    (ASSETS / "inundation_engine_spike.json").write_text(json.dumps(spike, indent=2))

    # 2) Improved pysheds borough depth
    borough_meta = run_borough_spike(
        dem_path=dem,
        rain_path=rain,
        bounds=bounds,
        out_dir=PROCESSED_DIR / "inundation",
        assets_dir=ASSETS,
        borough_id="south_queens",
        forcing_id="mrms_qpe_ida",
    )

    # Prefer borough depth for asset tables; fallback citywide MRMS depth
    depth_tif = Path(borough_meta["tif"])
    if not depth_tif.exists():
        depth_tif = PROCESSED_DIR / "inundation" / "depth_mrms_storm_total_m.tif"

    facilities = _ensure_facilities()
    roads = ASSETS / "roads.geojson"
    stations = ASSETS / "subway_stations.geojson"

    scenario = {
        "id": "ida_mrms_south_queens",
        "label": "Ida · MRMS QPE · South Queens (research)",
        "case_study": "Hurricane Ida remnants 2021-09-01",
        "forcing": "mrms_qpe_ida",
        "inundation_engine": borough_meta.get("engine"),
        "borough": "south_queens",
        "max_depth_m": borough_meta.get("max_m"),
        "wet_fraction": borough_meta.get("wet_fraction"),
    }

    risk = summarize_assets(depth_tif, roads, stations, facilities, scenario)
    risk["borough_inundation"] = borough_meta
    risk["engine_spike"] = {
        "conclusion": spike.get("conclusion"),
        "probes": spike.get("probes"),
    }

    out_json = ASSETS / "risk_depth_assets.json"
    out_json.write_text(json.dumps(risk, indent=2))
    (OUTPUTS_DIR / "risk_depth_assets.json").write_text(json.dumps(risk, indent=2))

    # Merge into product manifest
    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        manifest = json.loads(mp.read_text())
        manifest["risk"] = {
            "depth_assets": "risk_depth_assets.json",
            "scenario_id": scenario["id"],
            "official_nws": False,
            "decision_grade": False,
            "enterprise": False,
            "hens": False,
        }
        manifest["inundation_borough_spike"] = {
            "borough": "south_queens",
            "png": borough_meta.get("png"),
            "meta": f"depth_south_queens_mrms_qpe_ida_meta.json",
            "engine": borough_meta.get("engine"),
        }
        manifest["inundation_engine_spike"] = "inundation_engine_spike.json"
        mp.write_text(json.dumps(manifest, indent=2))

    print(json.dumps({"risk_table": risk["table"], "scenario": scenario["id"], "max_m": borough_meta.get("max_m")}, indent=2))


if __name__ == "__main__":
    main()
