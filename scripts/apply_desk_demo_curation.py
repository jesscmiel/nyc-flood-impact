#!/usr/bin/env python3
"""Re-curate Decision Desk for demos without resampling depth.

- Demote NJ Turnpike / non-NYC mainland noise in rank order
- Join Ida access-signal fixtures (DOT speeds / 511 / MTA alerts)
- Refresh GeoJSON properties + regenerate product_map.html
"""

from __future__ import annotations

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
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
FIXTURE = ASSETS / "access_signals_ida_fixture.json"


def _sync_geojson(payload: dict, geo_path: Path) -> None:
    if not geo_path.exists():
        return
    geo = json.loads(geo_path.read_text())
    by_id = {a["id"]: a for a in payload.get("assets") or []}
    for ft in geo.get("features") or []:
        props = ft.get("properties") or {}
        aid = props.get("id")
        if aid in by_id:
            # Keep geometry; refresh all desk props (rank, access, demotion).
            ft["properties"] = dict(by_id[aid])
    geo_path.write_text(json.dumps(geo))


def main() -> None:
    desk_json = ASSETS / "decision_desk_assets.json"
    desk_geo = ASSETS / "decision_desk_assets.geojson"
    if not desk_json.exists():
        raise SystemExit(f"missing {desk_json}")
    payload = json.loads(desk_json.read_text())
    fixture = load_access_fixture(FIXTURE) if FIXTURE.exists() else None
    buffer_m = float((fixture or {}).get("buffer_m") or 100.0)
    apply_access_and_demotion(payload, fixture, buffer_m=buffer_m)
    payload["listed_n"] = len(payload.get("assets") or [])
    desk_json.write_text(json.dumps(payload, indent=2))
    (OUTPUTS_DIR / "decision_desk_assets.json").write_text(desk_json.read_text())
    _sync_geojson(payload, desk_geo)

    # Point manifest at access fixture
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        manifest = json.loads(mp.read_text())
        desk = manifest.setdefault("asset_decision_desk", {})
        desk["access_signals_fixture"] = FIXTURE.name
        desk["demo_geography"] = "prefer_nyc_demote_nj_turnpike"
        mp.write_text(json.dumps(manifest, indent=2))

    html = None
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
        html = write_product_html(manifest, pluvial, validation)
    except Exception as exc:  # noqa: BLE001
        print(f"html regenerate skipped: {exc}")

    top = [
        {
            "rank": a["rank"],
            "name": a["name"],
            "depth_cm": a["max_depth_cm"],
            "demoted": a.get("demo_demoted"),
            "access": a.get("access_status"),
        }
        for a in (payload.get("assets") or [])[:8]
    ]
    shortlist = [
        a
        for a in payload.get("assets") or []
        if a["id"]
        in {
            "stations:194:Smith–9th Streets",
            "road:25430129",
            "facilities:40:Staten Island University Hospital",
            "road:37394898",
        }
    ]
    print(
        json.dumps(
            {
                "desk": str(desk_json),
                "fixture": str(FIXTURE) if fixture else None,
                "html": str(html) if html else None,
                "access_meta": payload.get("access_signals"),
                "top_after_demotion": top,
                "shortlist": [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "cm": a["max_depth_cm"],
                        "band": a["band"],
                        "access": a.get("access_status"),
                        "hint": a.get("action_hint"),
                    }
                    for a in shortlist
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
