#!/usr/bin/env python3
"""Reproducible Earth2 vs MRMS vs 311 validation summary (Track 5)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nyc_flash_flood_case_study.config import PROJECT_ROOT
from nyc_flash_flood_case_study.validation_product import build_validation_product


def main() -> None:
    parser = argparse.ArgumentParser(description="Build exploratory validation product JSON.")
    parser.add_argument(
        "--earth2-storm",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "earth2_precip" / "precip_storm_total.tif",
    )
    parser.add_argument(
        "--mrms-storm",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "mrms_qpe" / "mrms_qpe_storm_total.tif",
    )
    args = parser.parse_args()
    report = build_validation_product(
        args.earth2_storm,
        args.mrms_storm if args.mrms_storm.exists() else None,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
