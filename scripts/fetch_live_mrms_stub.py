#!/usr/bin/env python3
"""Phase F stub — live MRMS QPE hour smoke fetch (ops latency path prototype).

Generalizes the Ida replay URL pattern to "latest available" CONUS MultiSensor QPE
without rebuilding the full product stack. Second historical event + StormCast remain
out of scope unless separately scheduled.

Research only — NOT NWS warnings / NOT decision-grade.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nyc_flash_flood_case_study.config import OUTPUTS_DIR, RAW_DIR  # noqa: E402
from nyc_flash_flood_case_study.mrms_qpe_qa import QPE_PRODUCT, fetch_hourly_qpe  # noqa: E402

OUT = RAW_DIR / "rainfall" / "mrms_live_stub"


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def main() -> dict:
    parser = argparse.ArgumentParser(description="Smoke-fetch one live MRMS QPE hour.")
    parser.add_argument(
        "--valid-time",
        default=None,
        help="UTC hour to fetch (ISO). Default: previous complete UTC hour.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=6,
        help="If default hour missing, walk back up to N hours.",
    )
    args = parser.parse_args()

    if args.valid_time:
        target = _floor_hour(datetime.fromisoformat(args.valid_time.replace("Z", "+00:00")))
    else:
        # MRMS Pass1 often lags; start 2 h behind wall clock.
        target = _floor_hour(datetime.now(timezone.utc) - timedelta(hours=2))

    OUT.mkdir(parents=True, exist_ok=True)
    attempts: list[dict] = []
    chosen: Path | None = None
    chosen_time: datetime | None = None
    for back in range(max(1, args.lookback_hours)):
        ts = target - timedelta(hours=back)
        try:
            # fetch_hourly_qpe caches under the shared MRMS QPE cache dir
            path = fetch_hourly_qpe(ts)
            ok = path.exists() and path.stat().st_size > 1000
            attempts.append(
                {
                    "valid_time_utc": ts.isoformat(),
                    "path": str(path),
                    "ok": ok,
                    "bytes": path.stat().st_size if path.exists() else 0,
                }
            )
            if ok:
                chosen = path
                chosen_time = ts
                # Pointer copy into live_stub folder for ops path docs
                stub_copy = OUT / path.name
                if not stub_copy.exists():
                    stub_copy.write_bytes(path.read_bytes())
                break
        except Exception as exc:  # noqa: BLE001
            attempts.append(
                {
                    "valid_time_utc": ts.isoformat(),
                    "ok": False,
                    "error": str(exc),
                }
            )

    report = {
        "phase": "F",
        "product": "live_mrms_qpe_stub",
        "qpe_product": QPE_PRODUCT,
        "status": "ok" if chosen else "no_hour_found",
        "chosen_valid_time_utc": chosen_time.isoformat() if chosen_time else None,
        "chosen_path": str(chosen) if chosen else None,
        "attempts": attempts,
        "second_event": {
            "status": "not_run",
            "note": (
                "Second historical event through the full metro HAND pipeline is deferred — "
                "stub only documents live MRMS ingest generalization."
            ),
        },
        "pipeline_hook": (
            "Replay path: scripts/fetch_ida_mrms_hourly_metro.py (Ida fixed window). "
            "Live path: this stub → future regrid_mrms_to_metro(valid_time=…) → HAND. "
            "Earth2 live remains scripts/run_live_pipeline.py (scenario, not street precip)."
        ),
        "official_nws": False,
        "decision_grade": False,
        "honesty": (
            "Latency prototype only — does not rebuild Decision Desk or claim ops readiness."
        ),
    }
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUTS_DIR / "live_mrms_stub_meta.json"
    out_json.write_text(json.dumps(report, indent=2))
    (OUT / "live_mrms_stub_meta.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"status": report["status"], "valid": report["chosen_valid_time_utc"]}, indent=2))
    return report


if __name__ == "__main__":
    main()
