#!/usr/bin/env python3
"""Document (and optionally probe) higher-resolution precip paths.

Does **not** invent resolution. StormCast/CorrDiff require the Earth2Studio
environment and model weights; this script only reports what is available.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def probe_earth2studio(python_hint: str | None = None) -> dict:
    """Best-effort import probe using a caller-provided E2S interpreter note."""
    report = {
        "policy": "No fake downscaling. Prefer MRMS (~1 km) as observed reference; StormCast/CorrDiff only when weights run successfully.",
        "native_earth2_fcn": "~0.25° (PrecipitationAFNO on FCN states)",
        "mrms_qpe_local": str(PROJECT / "data" / "processed" / "mrms_qpe"),
        "hooks": {
            "stormcast": "earth2studio.models.px.StormCast / StormCastCONUS",
            "corrdiff": "earth2studio.models.dx.CorrDiff / CorrDiffEra5Hrrr / …",
            "run_with": "Use the Earth2Studio venv (e.g. /home/jesscmiel/projects/earth2studio/.venv/bin/python), not system Python.",
        },
        "python_hint": python_hint
        or "/home/jesscmiel/projects/earth2studio/.venv/bin/python",
        "imports": {},
    }
    try:
        import importlib

        px = importlib.import_module("earth2studio.models.px")
        dx = importlib.import_module("earth2studio.models.dx")
        report["imports"]["earth2studio"] = True
        report["imports"]["StormCast"] = hasattr(px, "StormCast")
        report["imports"]["StormCastCONUS"] = hasattr(px, "StormCastCONUS")
        report["imports"]["CorrDiff"] = hasattr(dx, "CorrDiff")
        report["imports"]["CorrDiffEra5Hrrr"] = hasattr(dx, "CorrDiffEra5Hrrr")
    except Exception as exc:  # noqa: BLE001
        report["imports"]["earth2studio"] = False
        report["imports"]["error"] = (
            f"{type(exc).__name__}: {exc}. Re-run under the Earth2Studio venv."
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        type=Path,
        default=PROJECT / "outputs" / "higher_res_precip_hooks.json",
        help="Where to write the JSON report",
    )
    args = parser.parse_args()
    report = probe_earth2studio()
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"Wrote {args.write}")


if __name__ == "__main__":
    main()
