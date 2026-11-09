#!/usr/bin/env python3
"""Build a clearly labeled synthetic/open drainage demo network.

Uses public OSM highways + NYC DEP catch-basin points (when available) to make
a **demo** catchment graph for susceptibility visualization only.

Never claims calibrated NYC sewer depths or official SWMM INP status.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point, mapping
from shapely.ops import unary_union

from nyc_flash_flood_case_study.extents import EXTENTS
from nyc_flash_flood_case_study.config import FIGURES_DIR, PROJECT_ROOT, RAW_DIR

ASSETS = FIGURES_DIR / "product_assets"
OUT = PROJECT_ROOT / "data" / "processed" / "drainage_demo"


def _load_roads(path: Path) -> list[LineString]:
    raw = json.loads(path.read_text())
    lines: list[LineString] = []
    if raw.get("type") == "FeatureCollection":
        for feat in raw.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") == "LineString":
                coords = [(c[0], c[1]) for c in geom["coordinates"]]
                if len(coords) >= 2:
                    lines.append(LineString(coords))
        return lines
    for el in raw.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        lines.append(LineString([(p["lon"], p["lat"]) for p in geom]))
    return lines


def _load_basins(path: Path) -> list[Point]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    # Skip SODA/API error payloads saved as JSON.
    if isinstance(raw, dict) and raw.get("errorCode"):
        return []
    pts: list[Point] = []
    feats = raw.get("features") if isinstance(raw, dict) else None
    if feats is None and isinstance(raw, dict) and "elements" in raw:
        for el in raw["elements"]:
            if "lat" in el and "lon" in el:
                pts.append(Point(el["lon"], el["lat"]))
        return pts
    for feat in feats or []:
        geom = feat.get("geometry") or {}
        if geom.get("type") == "Point":
            lon, lat = geom["coordinates"][:2]
            pts.append(Point(lon, lat))
    return pts


def build_demo(extent_id: str = "citywide") -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    bounds = EXTENTS[extent_id]["bounds"]
    bbox = (bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"])

    road_candidates = [
        RAW_DIR / "infrastructure" / "osm_highways_south_queens.json",
        ASSETS / "roads.geojson",
        FIGURES_DIR / "ida_v0_assets" / "roads.geojson",
    ]
    basin_candidates = [
        RAW_DIR / "infrastructure" / "osm_drains_south_queens.geojson",
        ASSETS / "catch_basins.geojson",
        FIGURES_DIR / "ida_v0_assets" / "catch_basins.geojson",
        RAW_DIR / "infrastructure" / "nycdep_catch_basins_south_queens.json",
    ]
    roads_path = next((p for p in road_candidates if p.exists()), None)
    roads = _load_roads(roads_path) if roads_path else []
    basins = []
    basins_path = None
    for path in basin_candidates:
        if not path.exists():
            continue
        loaded = _load_basins(path)
        if loaded:
            basins = loaded
            basins_path = path
            break

    # Clip to extent
    from shapely.geometry import box

    clip = box(*bbox)
    roads = [ln for ln in roads if ln.intersects(clip)]
    basins = [pt for pt in basins if clip.contains(pt)]

    # Synthetic nodes: subsample road vertices + real catch basins
    node_features = []
    for i, pt in enumerate(basins[:5000]):
        node_features.append(
            {
                "type": "Feature",
                "properties": {
                    "node_id": f"basin_{i}",
                    "source": "nyc_open_data_or_local_catch_basin",
                    "kind": "catch_basin",
                    "synthetic": False,
                    "demo_only": True,
                },
                "geometry": mapping(pt),
            }
        )
    # Add synthetic junctions along major roads every ~400 m
    synth = 0
    for line in roads[:: max(1, len(roads) // 800)]:
        if line.length <= 0:
            continue
        # length is in degrees; ~0.004° ≈ 400 m
        step = 0.004
        n = max(1, int(line.length / step))
        for i in range(n):
            pt = line.interpolate(i / n, normalized=True)
            if not clip.contains(pt):
                continue
            node_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "node_id": f"synth_junc_{synth}",
                        "source": "synthetic_from_osm_road",
                        "kind": "junction",
                        "synthetic": True,
                        "demo_only": True,
                    },
                    "geometry": mapping(pt),
                }
            )
            synth += 1
            if synth >= 1500:
                break
        if synth >= 1500:
            break

    # Synthetic conduits: short road segments as demo edges
    edge_features = []
    for i, line in enumerate(roads[:2500]):
        if line.length < 1e-6:
            continue
        edge_features.append(
            {
                "type": "Feature",
                "properties": {
                    "conduit_id": f"osm_road_{i}",
                    "source": "osm_highway_as_demo_conduit",
                    "synthetic": True,
                    "demo_only": True,
                    "disclaimer": "NOT a calibrated sewer pipe — OSM road centerline used as demo flow path only.",
                },
                "geometry": mapping(line.intersection(clip)),
            }
        )

    nodes = {"type": "FeatureCollection", "features": node_features}
    edges = {"type": "FeatureCollection", "features": edge_features}
    meta = {
        "label": "Synthetic / open drainage demo",
        "disclaimer": (
            "Demo-only urban drainage sketch from OSM roads + public catch-basin points. "
            "NOT a calibrated NYC DEP sewer model, NOT an official SWMM INP, NOT inundation depth."
        ),
        "extent_id": extent_id,
        "n_nodes": len(node_features),
        "n_conduits": len(edge_features),
        "n_catch_basins_realish": sum(1 for f in node_features if f["properties"]["kind"] == "catch_basin"),
        "n_synthetic_junctions": sum(1 for f in node_features if f["properties"]["synthetic"]),
        "roads_source": str(roads_path) if roads_path else None,
        "basins_source": str(basins_path) if basins_path else None,
        "swmm_status": "scaffold_only_no_calibrated_inp",
    }

    (OUT / "drainage_nodes.geojson").write_text(json.dumps(nodes))
    (OUT / "drainage_conduits.geojson").write_text(json.dumps(edges))
    (OUT / "drainage_demo_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "drainage_nodes.geojson").write_text(json.dumps(nodes))
    (ASSETS / "drainage_conduits.geojson").write_text(json.dumps(edges))
    (ASSETS / "drainage_demo_meta.json").write_text(json.dumps(meta, indent=2))

    # Minimal synthetic SWMM-like INP stub (documentation only — not runnable calibrated)
    stub = OUT / "synthetic_demo_network.NOTICE.txt"
    stub.write_text(
        "SYNTHETIC DEMO DRAINAGE NETWORK — NOT A CALIBRATED NYC SWMM MODEL\n"
        "Generated from OSM road centerlines + public catch-basin points.\n"
        "Do not use for emergency guidance or flood depths.\n"
        f"nodes={meta['n_nodes']} conduits={meta['n_conduits']}\n"
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extent", default="citywide")
    args = parser.parse_args()
    meta = build_demo(args.extent)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
