#!/usr/bin/env python3
"""Build validation scores JSON for the product map dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.validate.scores import score_points_on_depth
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR

ASSETS = FIGURES_DIR / "product_assets"


def main() -> None:
    depth = PROCESSED_DIR / "inundation" / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    if not depth.exists():
        depth = PROCESSED_DIR / "inundation" / "depth_mrms_storm_total_m.tif"
    scores = score_points_on_depth(
        depth_tif=depth,
        reports_geojson=ASSETS / "observed_311.geojson",
        gauges_geojson=ASSETS / "nwm_ahps_gauges.geojson",
        depth_hit_m=0.03,
    )
    (ASSETS / "validation_scores.json").write_text(json.dumps(scores, indent=2))
    (OUTPUTS_DIR / "validation_scores.json").write_text(json.dumps(scores, indent=2))

    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["validation_dashboard"] = {
            "scores": "validation_scores.json",
            "official": False,
            "certified_skill": False,
        }
        mp.write_text(json.dumps(m, indent=2))

    print(json.dumps({"summary": scores["summary"], "confidence": scores["confidence"]}, indent=2))


if __name__ == "__main__":
    main()
