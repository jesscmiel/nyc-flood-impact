#!/usr/bin/env python3
"""Attempt StormCast / CorrDiff for Ida over NYC; write an honest status report.

Prefer real model output. On failure, record the exact blocker — do not invent
higher-resolution precip fields.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "outputs" / "stormcast_corrdiff_attempt.json"


def _attempt_corrdiff(device: str) -> dict:
    status: dict = {
        "model": "CorrDiffEra5Hrrr",
        "target_time": "2021-09-01T18:00:00",
        "domain": "NYC / South Queens crop of CONUS HRRR grid",
        "status": "blocked",
    }
    try:
        import torch
        from earth2studio.data import GFS
        from earth2studio.models.dx import CorrDiffEra5Hrrr

        status["cuda"] = bool(torch.cuda.is_available())
        status["device_name"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
        package = CorrDiffEra5Hrrr.load_default_package()
        status["package"] = "CorrDiffEra5Hrrr.load_default_package()"
        model = CorrDiffEra5Hrrr.load_model(
            package,
            device=device,
            number_of_samples=1,
            distilled_model=True,
        )
        model = model.to(device)
        status["loaded"] = True
        # Minimal forward: fetch GFS IC and run one diagnostic sample.
        data = GFS()
        t0 = datetime(2021, 9, 1, 12, tzinfo=timezone.utc)
        # CorrDiffEra5Hrrr expects ERA5-like inputs via its input coords; GFS is a
        # practical IC source used in several E2S examples for 2021.
        from earth2studio.run import diagnostic as run_diagnostic
        from earth2studio.io import ZarrBackend

        zarr_path = PROJECT / "data" / "forecasts" / "corrdiff_ida_attempt.zarr"
        if zarr_path.exists():
            import shutil

            shutil.rmtree(zarr_path)
        io = ZarrBackend(file_name=str(zarr_path))
        run_diagnostic(
            time=[t0],
            nsteps=0,
            prognostic=None,
            diagnostic=model,
            data=data,
            io=io,
        )
        status["status"] = "done"
        status["output"] = str(zarr_path)
    except Exception as exc:  # noqa: BLE001
        status["status"] = "blocked"
        status["error_type"] = type(exc).__name__
        status["error"] = str(exc)
        status["traceback"] = traceback.format_exc()[-4000:]
    return status


def _attempt_stormcast(device: str) -> dict:
    status: dict = {
        "model": "StormCastCONUS",
        "target_init": "2021-09-01T12:00:00",
        "domain": "CONUS HRRR / NYC subset if supported",
        "status": "blocked",
    }
    try:
        import torch
        from earth2studio.data import GFS_FX
        from earth2studio.models.px import StormCastCONUS

        status["cuda"] = bool(torch.cuda.is_available())
        status["device_name"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
        package = StormCastCONUS.load_default_package()
        model = StormCastCONUS.load_model(
            package,
            conditioning_data_source=GFS_FX(),
        )
        model = model.to(device)
        status["loaded"] = True
        # One-step smoke: create iterator and take a single step if IC available.
        from earth2studio.data import HRRR
        from earth2studio.run import deterministic

        # StormCastCONUS typically needs HRRR-like ICs; try deterministic run helper.
        zarr_path = PROJECT / "data" / "forecasts" / "stormcast_ida_attempt.zarr"
        if zarr_path.exists():
            import shutil

            shutil.rmtree(zarr_path)
        from earth2studio.io import ZarrBackend

        io = ZarrBackend(file_name=str(zarr_path))
        # Prefer HRRR IC when available; fall back error is recorded honestly.
        data = HRRR()
        deterministic(
            time=[datetime(2021, 9, 1, 12, tzinfo=timezone.utc)],
            nsteps=1,
            prognostic=model,
            data=data,
            io=io,
        )
        status["status"] = "done"
        status["output"] = str(zarr_path)
    except Exception as exc:  # noqa: BLE001
        status["status"] = "blocked"
        status["error_type"] = type(exc).__name__
        status["error"] = str(exc)
        status["traceback"] = traceback.format_exc()[-4000:]
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--skip-stormcast", action="store_true")
    parser.add_argument("--skip-corrdiff", action="store_true")
    args = parser.parse_args()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": "No fake downscaling. Real model output only; otherwise blocked with reason.",
        "attempts": {},
    }
    if not args.skip_corrdiff:
        report["attempts"]["corrdiff"] = _attempt_corrdiff(args.device)
    if not args.skip_stormcast:
        report["attempts"]["stormcast"] = _attempt_stormcast(args.device)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2)[:4000])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
