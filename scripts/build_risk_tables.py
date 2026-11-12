#!/usr/bin/env python3
"""Build citywide (+ borough) depth×asset risk tables and hazard catalog hooks.

Research flood-risk MVP — no Enterprise / HENS. NOT official NWS.
Primary extent: NYC metro / citywide. South Queens retained as nested case study.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.exposure.geopackage import build_exposure_gpkg, intersect_depth_gpkg
from flood_risk.hazard.catalog import write_catalog
from flood_risk.inundation.engine_spike import try_build_sfincs_schema, write_spike_report
from flood_risk.inundation.pysheds_borough import run_borough_spike
from flood_risk.risk.depth_asset_tables import DEPTH_BANDS, summarize_assets
from flood_risk.risk.return_period import build_rp_placeholders
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

ASSETS = FIGURES_DIR / "product_assets"


def _ensure_facilities() -> Path:
    """Curated critical-facility demo points across NYC metro (research stub)."""
    out = ASSETS / "critical_facilities.geojson"
    pts = [
        # Queens / South Queens
        ("NYC Health + Hospitals / Elmhurst", "hospital", -73.8865, 40.7389),
        ("Jamaica Hospital Medical Center", "hospital", -73.8057, 40.7005),
        ("Queens Hospital Center", "hospital", -73.8250, 40.7170),
        ("Flushing Hospital Medical Center", "hospital", -73.8155, 40.7550),
        ("Forest Hills Hospital", "hospital", -73.8455, 40.7205),
        ("FDNY Engine 275", "fire", -73.8600, 40.7000),
        ("FDNY Engine 303", "fire", -73.7900, 40.7100),
        ("FDNY Engine 308", "fire", -73.8205, 40.6885),
        ("NYPD 103rd Precinct", "police", -73.8000, 40.6900),
        ("NYPD 105th Precinct", "police", -73.7400, 40.6700),
        ("NYPD 110th Precinct", "police", -73.8700, 40.7450),
        ("Citi Field", "venue", -73.8458, 40.7571),
        ("JFK Terminal 4 area", "transport", -73.7820, 40.6440),
        ("LIRR Jamaica Station", "transport", -73.8077, 40.6995),
        ("LIRR Far Rockaway", "transport", -73.7510, 40.6045),
        ("Aqueduct Racetrack area", "venue", -73.8285, 40.6725),
        # Brooklyn
        ("Brooklyn Hospital Center", "hospital", -73.9700, 40.6900),
        ("NYU Langone Brooklyn", "hospital", -74.0000, 40.6500),
        ("Coney Island Hospital", "hospital", -73.9660, 40.5860),
        ("Maimonides Medical Center", "hospital", -73.9985, 40.6395),
        ("Kings County Hospital", "hospital", -73.9445, 40.6565),
        ("Brookdale Hospital", "hospital", -73.9125, 40.6555),
        ("Barclays Center", "venue", -73.9760, 40.6826),
        ("FDNY Engine 276", "fire", -73.9605, 40.6350),
        ("NYPD 67th Precinct", "police", -73.9350, 40.6480),
        # Manhattan
        ("Bellevue Hospital", "hospital", -73.9750, 40.7390),
        ("NewYork-Presbyterian / Lower Manhattan", "hospital", -74.0050, 40.7100),
        ("Harlem Hospital", "hospital", -73.9400, 40.8140),
        ("Mount Sinai Hospital", "hospital", -73.9530, 40.7900),
        ("Lenox Hill Hospital", "hospital", -73.9605, 40.7735),
        ("Penn Station", "transport", -73.9935, 40.7506),
        ("Grand Central", "transport", -73.9772, 40.7527),
        ("Port Authority Bus Terminal", "transport", -73.9905, 40.7565),
        ("FDNY Rescue 1", "fire", -73.9965, 40.7540),
        # Bronx
        ("Lincoln Medical Center", "hospital", -73.9240, 40.8160),
        ("Jacobi Medical Center", "hospital", -73.8460, 40.8550),
        ("Montefiore Medical Center", "hospital", -73.8795, 40.8800),
        ("Bronx-Lebanon Hospital", "hospital", -73.9055, 40.8345),
        ("Yankee Stadium", "venue", -73.9262, 40.8296),
        ("NYPD 44th Precinct", "police", -73.9200, 40.8350),
        # Staten Island / NJ fringe
        ("Staten Island University Hospital", "hospital", -74.1000, 40.5850),
        ("Richmond University Medical Center", "hospital", -74.0960, 40.6355),
        ("Staten Island Ferry Terminal", "transport", -74.0720, 40.6430),
        ("FDNY Engine 151", "fire", -74.0850, 40.6150),
        ("Newark Liberty area", "transport", -74.1745, 40.6895),
        ("Jersey City Medical Center", "hospital", -74.0570, 40.7170),
        ("Hoboken University Medical Center", "hospital", -74.0305, 40.7415),
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
            "extent": "nyc_metro_citywide",
            "official": False,
        },
    }
    out.write_text(json.dumps(gj))
    return out


def _scenario_risk(
    *,
    extent_id: str,
    depth_tif: Path,
    roads: Path,
    stations: Path,
    facilities: Path,
    meta: dict,
    forcing: str = "mrms_qpe_ida",
) -> dict:
    label_ext = "NYC metro / citywide" if extent_id == "citywide" else extent_id.replace("_", " ").title()
    scenario = {
        "id": f"ida_mrms_{extent_id}",
        "label": f"Ida · MRMS QPE · {label_ext} (research)",
        "case_study": "Hurricane Ida remnants 2021-09-01",
        "forcing": forcing,
        "inundation_engine": meta.get("engine") or "pysheds_hand_bathtub",
        "extent_id": extent_id,
        "max_depth_m": meta.get("max_m"),
        "wet_fraction": meta.get("wet_fraction"),
    }
    # Prefer meta max if depth raster already exists from prior citywide build
    if scenario["max_depth_m"] is None and depth_tif.exists():
        import numpy as np
        import rasterio

        with rasterio.open(depth_tif) as ds:
            arr = ds.read(1)
            scenario["max_depth_m"] = float(np.nanmax(arr)) if np.isfinite(arr).any() else None
            scenario["wet_fraction"] = float(np.mean(arr > 0.005)) if np.isfinite(arr).any() else None

    risk = summarize_assets(depth_tif, roads, stations, facilities, scenario)
    risk["extent_id"] = extent_id
    risk["depth_tif"] = str(depth_tif)
    return risk


def main() -> None:
    dem = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
    rain = PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif"
    if not rain.exists():
        rain = PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif"

    facilities = _ensure_facilities()
    roads = ASSETS / "roads.geojson"
    stations = ASSETS / "subway_stations.geojson"

    # Exposure GeoPackage (citywide) + reliable intersects
    gpkg = ASSETS / "exposure_citywide.gpkg"
    exp_meta = build_exposure_gpkg(
        roads_geojson=roads,
        stations_geojson=stations,
        facilities_geojson=facilities,
        out_gpkg=gpkg,
    )
    (ASSETS / "exposure_citywide.json").write_text(json.dumps(exp_meta, indent=2))

    # Hazard catalog hooks (MRMS available; ERA5/GFS hooks)
    catalog = write_catalog(ASSETS / "hazard_catalog.json", PROJECT_ROOT)
    (OUTPUTS_DIR / "hazard_catalog.json").write_text(json.dumps(catalog, indent=2))

    # Engine spike (unchanged honesty)
    sq = EXTENTS["south_queens"]["bounds"]
    schema = try_build_sfincs_schema(
        OUTPUTS_DIR / "sfincs_spike_queens",
        (sq["xmin"], sq["ymin"], sq["xmax"], sq["ymax"]),
    )
    spike = write_spike_report(
        OUTPUTS_DIR / "inundation_engine_spike.json",
        {"sfincs_schema": schema, "primary_extent": "citywide", "forcing": "mrms_qpe_ida"},
    )
    (ASSETS / "inundation_engine_spike.json").write_text(json.dumps(spike, indent=2))

    # Citywide pysheds depth (primary)
    city_bounds = EXTENTS["citywide"]["bounds"]
    city_meta = run_borough_spike(
        dem_path=dem,
        rain_path=rain,
        bounds=city_bounds,
        out_dir=PROCESSED_DIR / "inundation",
        assets_dir=ASSETS,
        borough_id="citywide",
        forcing_id="mrms_qpe_ida",
    )
    city_depth = Path(city_meta["tif"])
    # Also keep prior citywide build as fallback alias
    legacy = PROCESSED_DIR / "inundation" / "depth_mrms_storm_total_m.tif"
    if not city_depth.exists() and legacy.exists():
        city_depth = legacy
        city_meta = {
            "engine": "pysheds_hand_bathtub",
            "max_m": None,
            "wet_fraction": None,
            "png": "depth_mrms_storm_total_m.png",
        }

    # South Queens nested case study
    sq_meta = run_borough_spike(
        dem_path=dem,
        rain_path=rain,
        bounds=sq,
        out_dir=PROCESSED_DIR / "inundation",
        assets_dir=ASSETS,
        borough_id="south_queens",
        forcing_id="mrms_qpe_ida",
    )

    city_risk = _scenario_risk(
        extent_id="citywide",
        depth_tif=city_depth,
        roads=roads,
        stations=stations,
        facilities=facilities,
        meta=city_meta,
    )
    sq_risk = _scenario_risk(
        extent_id="south_queens",
        depth_tif=Path(sq_meta["tif"]),
        roads=roads,
        stations=stations,
        facilities=facilities,
        meta=sq_meta,
    )

    # Prefer GPKG intersects for citywide (authoritative exposure path)
    gpkg_inter = intersect_depth_gpkg(gpkg, city_depth, DEPTH_BANDS)
    city_risk["exposure_gpkg"] = "exposure_citywide.gpkg"
    city_risk["exposure_intersects"] = gpkg_inter
    # Rebuild table rows from GPKG intersects for consistency
    city_risk["table"] = [
        {
            "band": b["id"],
            "label": b["label"],
            "min_m": b["min_m"],
            "max_m": b["max_m"],
            "roads": gpkg_inter["layers"]["roads"]["band_counts"][b["id"]],
            "stations": gpkg_inter["layers"]["stations"]["band_counts"][b["id"]],
            "facilities": gpkg_inter["layers"]["facilities"]["band_counts"][b["id"]],
        }
        for b in DEPTH_BANDS
    ]
    city_risk["wet_assets"] = {
        "roads": gpkg_inter["layers"]["roads"]["wet"],
        "stations": gpkg_inter["layers"]["stations"]["wet"],
        "facilities": gpkg_inter["layers"]["facilities"]["wet"],
    }
    city_risk["totals"] = {
        "roads": gpkg_inter["layers"]["roads"]["n"],
        "stations": gpkg_inter["layers"]["stations"]["n"],
        "facilities": gpkg_inter["layers"]["facilities"]["n"],
    }
    city_risk["max_depth_on_asset_m"] = {
        k: gpkg_inter["layers"][k]["max_depth_m"] for k in ("roads", "stations", "facilities")
    }

    city_risk["nested_case_studies"] = {"south_queens": "risk_depth_assets_south_queens.json"}
    city_risk["hazard_catalog"] = "hazard_catalog.json"
    city_risk["engine_spike"] = {"conclusion": spike.get("conclusion"), "probes": spike.get("probes")}
    city_risk["citywide_inundation"] = city_meta
    sq_risk["borough_inundation"] = sq_meta

    # Richer metrics + RP placeholders
    rp = build_rp_placeholders(PROJECT_ROOT, ASSETS)
    (OUTPUTS_DIR / "risk_return_period_placeholders.json").write_text(json.dumps(rp, indent=2))
    mrms_rp = next((s for s in rp["scenarios"] if s["id"] == "mrms_qpe_ida"), None)
    totals = city_risk["totals"]
    wet = city_risk["wet_assets"]
    city_risk["disruption_score"] = {
        "roads_wet_fraction": (wet["roads"] / totals["roads"]) if totals["roads"] else 0.0,
        "stations_wet_fraction": (wet["stations"] / totals["stations"]) if totals["stations"] else 0.0,
        "facilities_wet_fraction": (wet["facilities"] / totals["facilities"]) if totals["facilities"] else 0.0,
        "note": "Simple wet-asset fractions — research screening only.",
    }
    city_risk["return_period"] = {
        "file": "risk_return_period_placeholders.json",
        "event_placeholder": (mrms_rp or {}).get("return_period_placeholder"),
        "p99_precip_mm": (mrms_rp or {}).get("p99_precip_mm"),
        "era5_status": rp.get("era5", {}).get("status"),
        "honesty": rp.get("honesty"),
    }
    city_risk["scenario_card"] = {
        "title": city_risk["scenario"]["label"],
        "extent": "citywide",
        "max_depth_m": city_risk["scenario"].get("max_depth_m"),
        "wet_assets": wet,
        "disruption_score": city_risk["disruption_score"],
        "return_period_placeholder": city_risk["return_period"]["event_placeholder"],
        "confidence": "low — research prototype, uncalibrated RP placeholder, pysheds depth",
    }

    # Primary product file = citywide
    (ASSETS / "risk_depth_assets.json").write_text(json.dumps(city_risk, indent=2))
    (OUTPUTS_DIR / "risk_depth_assets.json").write_text(json.dumps(city_risk, indent=2))
    (ASSETS / "risk_depth_assets_south_queens.json").write_text(json.dumps(sq_risk, indent=2))
    (OUTPUTS_DIR / "risk_depth_assets_south_queens.json").write_text(json.dumps(sq_risk, indent=2))
    (ASSETS / "risk_scenarios.json").write_text(
        json.dumps(
            {
                "primary": "citywide",
                "scenarios": [
                    {"id": city_risk["scenario"]["id"], "file": "risk_depth_assets.json", "extent": "citywide"},
                    {
                        "id": sq_risk["scenario"]["id"],
                        "file": "risk_depth_assets_south_queens.json",
                        "extent": "south_queens",
                    },
                ],
                "official_nws": False,
                "decision_grade": False,
                "enterprise": False,
                "hens": False,
            },
            indent=2,
        )
    )

    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        manifest = json.loads(mp.read_text())
        manifest["risk"] = {
            "depth_assets": "risk_depth_assets.json",
            "depth_assets_south_queens": "risk_depth_assets_south_queens.json",
            "scenarios": "risk_scenarios.json",
            "return_period": "risk_return_period_placeholders.json",
            "scenario_id": city_risk["scenario"]["id"],
            "extent_default": "citywide",
            "official_nws": False,
            "decision_grade": False,
            "enterprise": False,
            "hens": False,
        }
        manifest["hazard_catalog"] = "hazard_catalog.json"
        manifest["exposure"] = {
            "gpkg": "exposure_citywide.gpkg",
            "meta": "exposure_citywide.json",
            "intersects": "exposure_depth_intersects.json",
            "layers": ["roads", "stations", "facilities"],
            "official": False,
        }
        manifest["inundation_citywide"] = {
            "png": city_meta.get("png"),
            "meta": "depth_citywide_mrms_qpe_ida_meta.json",
            "engine": city_meta.get("engine"),
            "extent": "citywide",
        }
        manifest["inundation_borough_spike"] = {
            "borough": "south_queens",
            "png": sq_meta.get("png"),
            "meta": "depth_south_queens_mrms_qpe_ida_meta.json",
            "engine": sq_meta.get("engine"),
        }
        manifest["inundation_engine_spike"] = "inundation_engine_spike.json"
        mp.write_text(json.dumps(manifest, indent=2))

    print(
        json.dumps(
            {
                "primary": "citywide",
                "citywide_table": city_risk["table"],
                "citywide_max_m": city_risk["scenario"].get("max_depth_m"),
                "south_queens_max_m": sq_risk["scenario"].get("max_depth_m"),
                "hazard_sources": [s["id"] for s in catalog["sources"]],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
