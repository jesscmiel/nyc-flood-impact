#!/usr/bin/env python3
"""Live-ish ops MVP: GFS IC → Earth2 precip → rebuild product map (Track 4).

Requires earth2studio installed in the active environment (GPU recommended).
Does NOT issue flood warnings — exposure-score style notes only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live-ish Earth2 → map pipeline.")
    parser.add_argument(
        "--init-time",
        default=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00:00"),
        help="UTC init time for GFS IC / Earth2 forecast",
    )
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--members", type=int, default=1)
    parser.add_argument("--skip-forecast", action="store_true", help="Rebuild map from existing NetCDF only")
    parser.add_argument("--with-mrms-qa", action="store_true")
    args = parser.parse_args()

    forecasts = ROOT / "data" / "forecasts"
    forecasts.mkdir(parents=True, exist_ok=True)
    stamp = args.init_time.replace(":", "").replace("-", "")
    global_nc = forecasts / f"earth2_precip_live_{stamp}.nc"
    clipped_nc = forecasts / f"nyc_precip_live_{stamp}.nc"

    meta = {
        "init_time": args.init_time,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "steps": args.steps,
        "members": args.members,
        "freshness_note": (
            "Forecast freshness equals GFS IC availability for init_time. "
            "Map layers are research exposure screens — never flood warnings."
        ),
        "auth_hosting": "Not included in MVP; static HTML + local/static hosting later.",
    }

    if not args.skip_forecast:
        try:
            import earth2studio  # noqa: F401
        except ImportError:
            raise SystemExit(
                "earth2studio is not installed in this environment. "
                "pip install -e /path/to/earth2studio (sibling checkout) then retry."
            )
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_earth2_forecast.py"),
            "--init-time",
            args.init_time,
            "--steps",
            str(args.steps),
            "--members",
            str(args.members),
            "--output",
            str(global_nc),
        ]
        print("Running", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(ROOT))
        # Normalize/clip via case-study forecast helper
        from nyc_flash_flood_case_study.forecast import normalize_earth2_forecast

        normalize_earth2_forecast(global_nc, clipped_nc)
        meta["global_forecast"] = str(global_nc)
        meta["clipped_forecast"] = str(clipped_nc)
    else:
        # Prefer Ida clipped demo if no live file
        clipped_nc = ROOT / "data" / "forecasts" / "nyc_precip_ida_20210901T12.nc"
        meta["clipped_forecast"] = str(clipped_nc)
        meta["note"] = "skip-forecast: rebuilt from existing clipped NetCDF"

    if args.with_mrms_qa and not args.skip_forecast:
        # Historical QPE QA only makes sense for historical inits; still allow for Ida window.
        build = [
            sys.executable,
            str(ROOT / "scripts" / "build_ida_v0_map.py"),
            "--global-forecast",
            str(global_nc),
            "--clipped-forecast",
            str(clipped_nc),
            "--with-mrms-qa",
            "--skip-infra",
        ]
        if args.skip_forecast:
            build = [
                sys.executable,
                str(ROOT / "scripts" / "build_ida_v0_map.py"),
                "--skip-normalize",
                "--skip-infra",
                "--clipped-forecast",
                str(clipped_nc),
                "--with-mrms-qa",
            ]
        print("Running", " ".join(build))
        subprocess.check_call(build, cwd=str(ROOT))
    elif args.with_mrms_qa:
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_ida_v0_map.py"),
                "--skip-normalize",
                "--skip-infra",
                "--clipped-forecast",
                str(clipped_nc),
                "--with-mrms-qa",
            ],
            cwd=str(ROOT),
        )

    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_product_map.py")], cwd=str(ROOT))
    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "run_validation_report.py")], cwd=str(ROOT))

    out = ROOT / "outputs" / "live_pipeline_meta.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {out}")
    print(f"Open figures/product_map.html (static server). Exposure scores only — not flood warnings.")


if __name__ == "__main__":
    main()
