#!/usr/bin/env python3
"""Fetch live NYC DOT speeds + 511-style closures + MTA alerts for Decision Desk.

Writes ``figures/product_assets/access_signals_live.json``.
Falls back to Ida fixture content when live sources fail.

  .venv/bin/python scripts/fetch_live_access_feeds.py
  .venv/bin/python scripts/fetch_live_access_feeds.py --apply-desk

Optional: export NYSDOT_511_API_KEY for real 511 GetEvents (else NYC street closures).
Research only — NOT official closures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.risk.access_signals import (  # noqa: E402
    apply_access_and_demotion,
    load_access_fixture,
)
from flood_risk.risk.live_access_feeds import (  # noqa: E402
    build_live_access_fixture,
    merge_live_over_fixture,
    write_live_fixture,
)
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
FIXTURE = ASSETS / "access_signals_ida_fixture.json"
LIVE_OUT = ASSETS / "access_signals_live.json"


def main() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply-desk",
        action="store_true",
        help="Re-join live(+fixture joins) onto decision_desk_assets.json",
    )
    parser.add_argument(
        "--no-merge-fixture-joins",
        action="store_true",
        help="Do not retain Ida fixture explicit joins",
    )
    args = parser.parse_args()

    fixture = load_access_fixture(FIXTURE) if FIXTURE.exists() else None
    live = build_live_access_fixture(fixture_fallback=fixture)
    if fixture and not args.no_merge_fixture_joins and live.get("mode") == "live":
        live = merge_live_over_fixture(live, fixture)
    write_live_fixture(LIVE_OUT, live)
    (OUTPUTS_DIR / "access_signals_live.json").write_text(LIVE_OUT.read_text())

    result: dict = {
        "wrote": str(LIVE_OUT),
        "mode": (live.get("live_status") or {}).get("mode") or live.get("mode"),
        "n_dot": len(live.get("dot_speeds") or []),
        "n_511": len(live.get("events_511") or []),
        "n_mta": len(live.get("mta_alerts") or []),
        "live_status": live.get("live_status"),
    }

    if args.apply_desk:
        desk_json = ASSETS / "decision_desk_assets.json"
        desk_geo = ASSETS / "decision_desk_assets.geojson"
        if not desk_json.exists():
            raise SystemExit(f"missing {desk_json}")
        payload = json.loads(desk_json.read_text())
        buffer_m = float(live.get("buffer_m") or 120.0)
        apply_access_and_demotion(payload, live, buffer_m=buffer_m)
        payload["listed_n"] = len(payload.get("assets") or [])
        desk_json.write_text(json.dumps(payload, indent=2))
        (OUTPUTS_DIR / "decision_desk_assets.json").write_text(desk_json.read_text())
        if desk_geo.exists():
            geo = json.loads(desk_geo.read_text())
            by_id = {a["id"]: a for a in payload.get("assets") or []}
            for ft in geo.get("features") or []:
                props = ft.get("properties") or {}
                aid = props.get("id")
                if aid in by_id:
                    ft["properties"] = dict(by_id[aid])
            desk_geo.write_text(json.dumps(geo))
        for name in ("product_manifest.json", "manifest.json"):
            mp = ASSETS / name
            if not mp.exists():
                continue
            manifest = json.loads(mp.read_text())
            desk = manifest.setdefault("asset_decision_desk", {})
            desk["access_signals_live"] = LIVE_OUT.name
            desk["access_signals_fixture"] = FIXTURE.name
            desk["access_signals_default"] = "fixture"
            mp.write_text(json.dumps(manifest, indent=2))
        result["desk"] = str(desk_json)
        result["access_meta"] = payload.get("access_signals")

    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
