#!/usr/bin/env python3
"""Build Asset Decision Desk ranked wet-asset JSON + GeoJSON (Ida / MRMS → pysheds)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.risk.ranked_assets import build_ranked_assets, write_ranked_assets
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR

ASSETS = FIGURES_DIR / "product_assets"


def main() -> None:
    gpkg = ASSETS / "exposure_citywide.gpkg"
    depth = PROCESSED_DIR / "inundation" / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    if not depth.exists():
        depth = PROCESSED_DIR / "inundation" / "depth_mrms_storm_total_m.tif"
    if not gpkg.exists():
        raise SystemExit(f"missing exposure gpkg: {gpkg}")
    if not depth.exists():
        raise SystemExit(f"missing depth tif: {depth}")

    lead_tifs = [
        (6.0, PROCESSED_DIR / "inundation" / "depth_mrms_cum_lead_06h_m.tif"),
        (12.0, PROCESSED_DIR / "inundation" / "depth_mrms_cum_lead_12h_m.tif"),
        (18.0, PROCESSED_DIR / "inundation" / "depth_mrms_cum_lead_18h_m.tif"),
        (24.0, PROCESSED_DIR / "inundation" / "depth_mrms_cum_lead_24h_m.tif"),
    ]

    print("Building ranked wet assets (pysheds citywide × GPKG)…")
    payload = build_ranked_assets(
        gpkg=gpkg,
        depth_tif=depth,
        lead_tifs=lead_tifs,
        top_n=None,  # all wet assets for filterable desk
    )
    out_json = ASSETS / "decision_desk_assets.json"
    out_geo = ASSETS / "decision_desk_assets.geojson"
    write_ranked_assets(payload, out_json, out_geo)
    (OUTPUTS_DIR / "decision_desk_assets.json").write_text(out_json.read_text())

    # Patch product_manifest with desk pointers + depth engine labels
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        manifest = json.loads(mp.read_text())
        manifest["asset_decision_desk"] = {
            "assets_json": "decision_desk_assets.json",
            "assets_geojson": "decision_desk_assets.geojson",
            "primary_depth_engine": "pysheds_hand_bathtub_v2",
            "primary_forcing": "mrms_qpe_ida",
            "default_ux": "susceptibility_then_affected_assets",
            "official_nws": False,
            "decision_grade": False,
        }
        manifest["depth_engines"] = payload.get("depth_engines_reconcile")
        mp.write_text(json.dumps(manifest, indent=2))

    # Regenerate product map HTML (Asset Decision Desk UX)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from product_map_html import write_product_html

        manifest = json.loads((ASSETS / "product_manifest.json").read_text())
        if (ASSETS / "depth_sfincs_queens_ida_m.png").exists():
            meta_path = ASSETS / "depth_sfincs_queens_ida_meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            manifest["inundation_sfincs"] = {
                "png": "depth_sfincs_queens_ida_m.png",
                "meta": "depth_sfincs_queens_ida_meta.json",
                "engine": meta.get("engine", "sfincs_docker"),
                "role": "alternate_hydro_track",
                "honesty": "NOT peer-authoritative with pysheds citywide.",
                "extent": "south_queens",
            }
            (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
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
        html = None
        print(f"html regenerate skipped: {exc}")

    print(
        json.dumps(
            {
                "wrote": str(out_json),
                "geojson": str(out_geo),
                "html": str(html) if html else None,
                "wet_total": payload["counts"]["wet_total"],
                "top": [
                    {
                        "rank": a["rank"],
                        "name": a["name"],
                        "type": a["asset_type"],
                        "depth_cm": a["max_depth_cm"],
                        "band": a["band_label"],
                        "lead_h": a["first_exceedance_lead_h"],
                    }
                    for a in payload["assets"][:8]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
