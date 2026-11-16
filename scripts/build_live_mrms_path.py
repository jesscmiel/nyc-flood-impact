#!/usr/bin/env python3
"""P2.7 — Live MRMS QPF/QPE ops-latency path (+ fixture honesty).

Fetches the latest available CONUS MultiSensor QPE hour from NOAA S3 when
reachable; always writes a Decision Desk status artifact that labels what is
**live** vs **Ida/Henri fixture replay**.

Does not rebuild HAND ranks or claim ops readiness / NWS warnings.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_live_mrms_stub import main as fetch_live  # noqa: E402
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR  # noqa: E402
from nyc_flash_flood_case_study.mrms_qpe_qa import QPE_PRODUCT  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"


def main() -> dict:
    live = fetch_live()
    fixture = {
        "ida": {
            "role": "default_decision_desk_replay",
            "storm_path_id": "mrms_qpe_ida",
            "init_time_utc": "2021-09-01T12:00:00Z",
            "live": False,
            "note": "Ida MRMS QPE hourly loop shipped in product_assets — fixture replay.",
        },
        "henri": {
            "role": "second_storm_research_replay",
            "storm_path_id": "mrms_qpe_henri",
            "init_time_utc": "2021-08-21T18:00:00Z",
            "live": False,
            "note": "Henri MRMS QPE loop after make henri-parity — fixture replay.",
        },
    }
    status = {
        "product": "live_mrms_qpf_path",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "qpe_product": QPE_PRODUCT,
        "source": "https://noaa-mrms-pds.s3.amazonaws.com/CONUS/",
        "live_fetch": {
            "status": live.get("status"),
            "chosen_valid_time_utc": live.get("chosen_valid_time_utc"),
            "chosen_path": live.get("chosen_path"),
            "reachable": live.get("status") == "ok",
            "attempts_n": len(live.get("attempts") or []),
        },
        "fixtures": fixture,
        "ops_latency_story": (
            "Live path smoke-fetches the latest Pass1 MultiSensor QPE hour (often ~1–2 h lag). "
            "Decision Desk default remains Ida fixture replay; live hour is an Advanced ops probe, "
            "not a rebuilt HAND desk."
        ),
        "rebuild_hook": (
            "Future: regrid live hour → metro DEM → drainage proxy → HAND cum frame. "
            "Not wired into default UX in this ship."
        ),
        "official_nws": False,
        "decision_grade": False,
        "honesty": (
            "Live MRMS QPE probe vs labeled Ida/Henri fixture loops — research latency path only. "
            "NOT NWS QPF watch/warning / NOT decision-grade ops."
        ),
    }
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "live_mrms_status.json").write_text(json.dumps(status, indent=2))
    (OUTPUTS_DIR / "live_mrms_status.json").write_text(json.dumps(status, indent=2))
    # Keep stub meta alongside
    if (OUTPUTS_DIR / "live_mrms_stub_meta.json").exists():
        status["stub_meta"] = "outputs/live_mrms_stub_meta.json"

    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["live_mrms"] = {
            "status_json": "live_mrms_status.json",
            "available": bool(status["live_fetch"]["reachable"]),
            "valid_time_utc": status["live_fetch"]["chosen_valid_time_utc"],
            "qpe_product": QPE_PRODUCT,
            "default_ux": "ida_fixture_replay",
            "honesty": status["honesty"],
        }
        mp.write_text(json.dumps(m, indent=2))

    docs = ROOT / "docs" / "live-mrms-qpf-path.md"
    docs.write_text(
        f"""# Live MRMS QPF/QPE path (P2.7)

**Research ops-latency probe** — NOT NWS / NOT decision-grade.

## What is live vs fixture

| Surface | Live? | Notes |
| --- | --- | --- |
| Decision Desk default radar | **Fixture** | Ida MRMS QPE 0–36h replay (`mrms_qpe_ida`) |
| Henri Event switch | **Fixture** | Henri MRMS 0–24h after `make henri-parity` |
| Advanced live probe | **Live when reachable** | Latest NOAA S3 MultiSensor QPE Pass1 hour |

## Reproduce

```bash
make live-mrms
# or
.venv/bin/python scripts/build_live_mrms_path.py
```

Status artifact: `figures/product_assets/live_mrms_status.json`

Last run: live status = `{status["live_fetch"]["status"]}` · valid = `{status["live_fetch"]["chosen_valid_time_utc"]}`.

## Honesty

Live fetch does **not** rebuild HAND ranks or swap the default desk loop.
Product QPE product id: `{QPE_PRODUCT}`.
"""
    )

    try:
        from product_map_html import write_product_html

        manifest = json.loads((ASSETS / "product_manifest.json").read_text())
        pluvial = (
            json.loads((ASSETS / "pluvial_meta.json").read_text())
            if (ASSETS / "pluvial_meta.json").exists()
            else {}
        )
        validation = (
            json.loads((ASSETS / "validation_product.json").read_text())
            if (ASSETS / "validation_product.json").exists()
            else {}
        )
        write_product_html(manifest, pluvial, validation)
    except Exception as exc:  # noqa: BLE001
        print(f"html regen skipped: {exc}")

    print(json.dumps({"live": status["live_fetch"], "doc": str(docs)}, indent=2))
    return status


if __name__ == "__main__":
    main()
