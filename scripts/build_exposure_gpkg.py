#!/usr/bin/env python3
"""Build citywide exposure GeoPackage and prove reliable depth intersects."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.exposure.geopackage import build_exposure_gpkg, intersect_depth_gpkg
from flood_risk.risk.depth_asset_tables import DEPTH_BANDS
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR

ASSETS = FIGURES_DIR / "product_assets"


def main() -> None:
    roads = ASSETS / "roads.geojson"
    stations = ASSETS / "subway_stations.geojson"
    facilities = ASSETS / "critical_facilities.geojson"
    for p in (roads, stations, facilities):
        if not p.exists():
            raise SystemExit(f"missing {p}")

    gpkg = ASSETS / "exposure_citywide.gpkg"
    meta = build_exposure_gpkg(
        roads_geojson=roads,
        stations_geojson=stations,
        facilities_geojson=facilities,
        out_gpkg=gpkg,
    )
    (OUTPUTS_DIR / "exposure_citywide.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "exposure_citywide.json").write_text(json.dumps(meta, indent=2))

    depth = PROCESSED_DIR / "inundation" / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    if not depth.exists():
        depth = PROCESSED_DIR / "inundation" / "depth_mrms_storm_total_m.tif"
    inter = intersect_depth_gpkg(gpkg, depth, DEPTH_BANDS)
    inter["official_nws"] = False
    inter["decision_grade"] = False
    inter["enterprise"] = False
    inter["hens"] = False
    (ASSETS / "exposure_depth_intersects.json").write_text(json.dumps(inter, indent=2))
    (OUTPUTS_DIR / "exposure_depth_intersects.json").write_text(json.dumps(inter, indent=2))

    # Manifest pointer
    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["exposure"] = {
            "gpkg": "exposure_citywide.gpkg",
            "meta": "exposure_citywide.json",
            "intersects": "exposure_depth_intersects.json",
            "layers": ["roads", "stations", "facilities"],
            "official": False,
        }
        mp.write_text(json.dumps(m, indent=2))

    # Fail hard if any layer missing intersects
    for layer, stats in inter["layers"].items():
        assert stats["n"] > 0, layer
        assert "band_counts" in stats, layer
    print(json.dumps({"gpkg": str(gpkg), "layers": meta["layers"], "intersects": inter["layers"]}, indent=2))


if __name__ == "__main__":
    main()
