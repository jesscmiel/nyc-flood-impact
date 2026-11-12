#!/usr/bin/env python3
"""Wire metro rebuild outputs into product manifests + regenerate Decision Desk HTML."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import DEFAULT_MAP_EXTENT, EXTENTS, PRIMARY_DATA_EXTENT

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"


def main() -> dict:
    depth_meta_path = ASSETS / "depth_metro_mrms_qpe_ida_meta.json"
    if not depth_meta_path.exists():
        depth_meta_path = ASSETS / "depth_citywide_mrms_qpe_ida_meta.json"
    depth_meta = json.loads(depth_meta_path.read_text()) if depth_meta_path.exists() else {}
    inundation_meta = (
        json.loads((ASSETS / "inundation_meta.json").read_text())
        if (ASSETS / "inundation_meta.json").exists()
        else depth_meta
    )
    sfincs_meta = (
        json.loads((ASSETS / "depth_sfincs_queens_ida_meta.json").read_text())
        if (ASSETS / "depth_sfincs_queens_ida_meta.json").exists()
        else {}
    )
    b = EXTENTS[PRIMARY_DATA_EXTENT]["bounds"]
    leaflet = [[b["ymin"], b["xmin"]], [b["ymax"], b["xmax"]]]

    primary_png = "depth_metro_mrms_qpe_ida_storm_total_m.png"
    if not (ASSETS / primary_png).exists():
        primary_png = "depth_citywide_mrms_qpe_ida_storm_total_m.png"

    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["primary_depth"] = {
            "engine": "pysheds_hand_bathtub_v2",
            "extent": PRIMARY_DATA_EXTENT,
            "forcing": depth_meta.get(
                "forcing_kind", "spatial_mrms_qpe_ida_minus_drainage_capacity_proxy"
            ),
            "drainage_capacity_proxy": depth_meta.get("drainage_capacity_proxy"),
            "png": primary_png,
            "meta": depth_meta_path.name,
            "role": "primary",
            "honesty": depth_meta.get("disclaimer")
            or "Primary research depth — NOT NWS / NOT decision-grade / NOT DEP sewer.",
        }
        m["inundation"] = inundation_meta
        m["inundation_citywide"] = {
            "png": primary_png,
            "meta": depth_meta_path.name,
            "extent": PRIMARY_DATA_EXTENT,
            "engine": "pysheds_hand_bathtub_v2",
            "role": "primary_depth",
            "bounds": leaflet,
        }
        if (ASSETS / "depth_sfincs_queens_ida_m.png").exists():
            m["inundation_sfincs"] = {
                "png": "depth_sfincs_queens_ida_m.png",
                "meta": "depth_sfincs_queens_ida_meta.json",
                "engine": sfincs_meta.get("engine", "sfincs_docker"),
                "extent": "south_queens",
                "role": "advanced_research_hydro_nest",
                "primary": False,
                "honesty": sfincs_meta.get("honesty")
                or "Advanced research hydro nest — not peer-authoritative with primary HAND.",
            }
        nested_png = ASSETS / "depth_sfincs_metro_nested_ida_m.png"
        if nested_png.exists():
            nested_meta = (
                json.loads((ASSETS / "depth_sfincs_metro_nested_ida_meta.json").read_text())
                if (ASSETS / "depth_sfincs_metro_nested_ida_meta.json").exists()
                else {}
            )
            m["inundation_sfincs_nested"] = {
                "png": nested_png.name,
                "meta": "depth_sfincs_metro_nested_ida_meta.json",
                "engine": nested_meta.get("engine", "sfincs_metro_nested_v1"),
                "extent": "metro",
                "bounds": leaflet,
                "role": "advanced_research_hydro",
                "primary": False,
                "not_swmm": True,
                "honesty": nested_meta.get("honesty")
                or "Metro nested SFINCS — Advanced research hydro; HAND stays primary; no SWMM.",
            }
            m["advanced_research_hydro"] = {
                "id": "sfincs_metro_nested_v1",
                "png": nested_png.name,
                "primary_remains": "pysheds_hand_bathtub_v2",
                "not_swmm": True,
            }
        lb = m.get("layer_bounds") or {}
        lb.update(
            {
                "map_extent_default": DEFAULT_MAP_EXTENT,
                "data_domain": PRIMARY_DATA_EXTENT,
                "data_domain_bounds": leaflet,
                "inundation": leaflet,
                "precip": leaflet,
                "susceptibility": leaflet,
                "note": "metro = continuous soft-edge overlays for precip/susc/depth",
            }
        )
        m["layer_bounds"] = lb
        # Keep storm-path overlay bounds aligned with metro depth (no citywide inset box)
        for p in m.get("storm_paths") or []:
            if p.get("id") == "mrms_qpe_ida" or p.get("ida_primary_viz"):
                if isinstance(p.get("precip"), dict):
                    p["precip"]["bounds"] = leaflet
                    p["precip"]["extent"] = PRIMARY_DATA_EXTENT
                if isinstance(p.get("susceptibility"), dict):
                    p["susceptibility"]["bounds"] = leaflet
                    p["susceptibility"]["extent"] = PRIMARY_DATA_EXTENT
        if isinstance(m.get("precip"), dict):
            m["precip"]["bounds"] = leaflet
        if isinstance(m.get("susceptibility"), dict):
            m["susceptibility"]["bounds"] = leaflet
        m["depth_engines"] = {
            "primary": m["primary_depth"],
            "alternate": m.get("inundation_sfincs"),
        }
        mp.write_text(json.dumps(m, indent=2))

    # Refresh Decision Desk + HTML
    from build_decision_desk_assets import main as build_desk

    build_desk()

    audit = PROJECT_ROOT / "outputs" / "science_audit_recompute.json"
    return {
        "primary_png": primary_png,
        "extent": PRIMARY_DATA_EXTENT,
        "audit_exists": audit.exists(),
        "sfincs_png": (ASSETS / "depth_sfincs_queens_ida_m.png").exists(),
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
