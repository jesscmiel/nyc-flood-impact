#!/usr/bin/env python3
"""Build Ida research corridor impassability graph (P2.3).

Wet HAND road edges → landmark connectivity among Smith-9 / Brooklyn Hospital / Myrtle.
Labeled research — NOT official DOT closures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.risk.corridor_graph import build_corridor_payload  # noqa: E402
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"


def main() -> dict:
    gpkg = ASSETS / "exposure_citywide.gpkg"
    depth = PROCESSED_DIR / "inundation" / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not depth.exists():
        depth = PROCESSED_DIR / "inundation" / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    if not gpkg.exists() or not depth.exists():
        raise SystemExit(f"missing gpkg/depth: {gpkg.exists()} {depth.exists()}")

    payload = build_corridor_payload(gpkg=gpkg, depth_tif=depth)
    wet_geo = payload.pop("corridors_geo")
    path_geos = payload.pop("path_geos")

    (ASSETS / "corridor_impassability.json").write_text(json.dumps(payload, indent=2))
    (ASSETS / "corridor_wet_edges.geojson").write_text(json.dumps(wet_geo))
    # Merge research paths into one FeatureCollection with pair labels
    merged_feats = []
    for key, fc in path_geos.items():
        for ft in fc.get("features") or []:
            props = dict(ft.get("properties") or {})
            props["pair"] = key
            merged_feats.append({"type": "Feature", "properties": props, "geometry": ft.get("geometry")})
    (ASSETS / "corridor_research_paths.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": merged_feats})
    )
    (OUTPUTS_DIR / "corridor_impassability.json").write_text(
        (ASSETS / "corridor_impassability.json").read_text()
    )

    # Patch manifests
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["corridor_impassability"] = {
            "json": "corridor_impassability.json",
            "wet_edges_geojson": "corridor_wet_edges.geojson",
            "paths_geojson": "corridor_research_paths.geojson",
            "available": True,
            "n_pairs": len(payload.get("pairs") or []),
            "statuses": [p.get("status") for p in (payload.get("pairs") or [])],
            "honesty": payload.get("honesty"),
            "official_closures": False,
        }
        desk = m.setdefault("asset_decision_desk", {})
        desk["corridor_impassability_json"] = "corridor_impassability.json"
        mp.write_text(json.dumps(m, indent=2))

    # Regenerate HTML
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

    summary = {
        "out": "corridor_impassability.json",
        "graph_stats": payload.get("graph_stats"),
        "pairs": [
            {
                "from": p.get("from_name"),
                "to": p.get("to_name"),
                "status": p.get("status"),
                "delta_m": p.get("delta_m_vs_open"),
            }
            for p in payload.get("pairs") or []
        ],
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
