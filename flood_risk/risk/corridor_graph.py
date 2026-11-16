"""Research corridor impassability graph from wet road segments.

Prefer NYC LION street topology (NodeIDFrom/To) when available; fall back to
exposure GPKG LineStrings. Marks edges impassable when HAND depth ≥ research
band thresholds and reports landmark connectivity.

Labeled research only — NOT official DOT closures / NOT decision-grade.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import LineString, mapping

from flood_risk.exposure.geopackage import LAYER_ROADS
from flood_risk.risk.ranked_assets import _asset_id, _asset_name, _sample_depth

DEFAULT_NODE_QUANT = 0.00035
DEEP_M = 0.08
POND_M = 0.03
DEFAULT_LION_GDB = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "lion"
    / "extract"
    / "lion"
    / "lion.gdb"
)


@dataclass(frozen=True)
class Landmark:
    id: str
    name: str
    lon: float
    lat: float
    kind: str = "landmark"


def _quantize(lon: float, lat: float, q: float) -> tuple[float, float]:
    return (round(lon / q) * q, round(lat / q) * q)


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def default_ida_landmarks() -> list[Landmark]:
    return [
        Landmark(
            id="stations:gtfs:F22",
            name="Smith-9 Sts",
            lon=-73.995959,
            lat=40.67358,
            kind="station",
        ),
        Landmark(
            id="facilities:uid:a464e8e63eb8b2c92ab1995735cfd284",
            name="Brooklyn Hospital Downtown",
            lon=-73.977890749,
            lat=40.6906384129,
            kind="facility",
        ),
        Landmark(
            id="road:37394898",
            name="Myrtle Avenue (wet corridor)",
            lon=-73.98045025137438,
            lat=40.693540113644346,
            kind="road",
        ),
    ]


def _densify_coords(coords: list[tuple[float, float]], step_m: float = 90.0) -> list[tuple[float, float]]:
    if len(coords) < 2:
        return coords
    out: list[tuple[float, float]] = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        dist = _haversine_m(a, b)
        if dist <= step_m:
            out.append(b)
            continue
        n = max(1, int(math.ceil(dist / step_m)))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def build_lion_graph(
    *,
    depth_tif,
    bbox: tuple[float, float, float, float],
    lion_gdb: Path | None = None,
) -> dict[str, Any] | None:
    gdb = Path(lion_gdb) if lion_gdb else DEFAULT_LION_GDB
    if not gdb.exists():
        return None
    minx, miny, maxx, maxy = bbox
    # Read nodes, project to WGS84, clip
    nodes_gdf = gpd.read_file(gdb, layer="node")
    if nodes_gdf.crs is None:
        nodes_gdf = nodes_gdf.set_crs(2263)
    nodes_gdf = nodes_gdf.to_crs(4326)
    nodes_gdf = nodes_gdf.cx[minx:maxx, miny:maxy]
    if nodes_gdf.empty:
        return None
    node_ids = set(str(v).zfill(7) if str(v).isdigit() else str(v) for v in nodes_gdf["NODEID"].tolist())
    node_xy: dict[str, tuple[float, float]] = {}
    for _, row in nodes_gdf.iterrows():
        nid = str(row["NODEID"])
        if nid.isdigit():
            nid = nid.zfill(7)
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        node_xy[nid] = (float(geom.x), float(geom.y))

    # LION segments intersecting bbox (read + filter in WGS84)
    lion = gpd.read_file(gdb, layer="lion")
    if lion.crs is None:
        lion = lion.set_crs(2263)
    lion = lion.to_crs(4326)
    lion = lion.cx[minx:maxx, miny:maxy]
    # Keep generic street centerlines; drop non-road feature types when present.
    if "FeatureTyp" in lion.columns:
        # 0 = street segment in LION docs; keep unknowns too if blank
        lion = lion[lion["FeatureTyp"].isna() | (lion["FeatureTyp"].astype(str).isin(["0", "1", "2", "3", "A", "W"]))]
    if lion.empty:
        return None

    nodes: dict[str, dict[str, Any]] = {
        nid: {"id": f"lion:{nid}", "lon": xy[0], "lat": xy[1], "lion_node": nid}
        for nid, xy in node_xy.items()
    }
    edges: list[dict[str, Any]] = []
    with rasterio.open(depth_tif) as ds:
        for _, row in lion.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            u_raw = str(row.get("NodeIDFrom") or "")
            v_raw = str(row.get("NodeIDTo") or "")
            if u_raw.isdigit():
                u_raw = u_raw.zfill(7)
            if v_raw.isdigit():
                v_raw = v_raw.zfill(7)
            if u_raw not in node_xy or v_raw not in node_xy:
                continue
            depth, _off = _sample_depth(ds, geom, LAYER_ROADS)
            depth_m = float(depth) if np.isfinite(depth) else 0.0
            u = f"lion:{u_raw}"
            v = f"lion:{v_raw}"
            if u == v:
                continue
            seg = str(row.get("SegmentID") or f"seg-{len(edges)}")
            name = str(row.get("Street") or row.get("SAFStreetName") or f"LION {seg}")
            length_m = _haversine_m(node_xy[u_raw], node_xy[v_raw])
            try:
                length_m = max(length_m, float(geom.length) * 111_000.0 * 0.8)
            except Exception:  # noqa: BLE001
                pass
            edges.append(
                {
                    "id": f"lion:{seg}",
                    "road_id": f"lion:{seg}",
                    "name": name.title() if name == name.upper() else name,
                    "highway": "lion_street",
                    "u": u,
                    "v": v,
                    "length_m": round(max(length_m, 1.0), 1),
                    "depth_m": round(depth_m, 4),
                    "depth_cm": round(depth_m * 100.0, 1),
                    "impassable_deep": depth_m >= DEEP_M,
                    "impassable_pond": depth_m >= POND_M,
                    "geometry": mapping(LineString([node_xy[u_raw], node_xy[v_raw]])),
                    "source": "lion",
                }
            )

    if len(edges) < 20:
        return None
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "topology": "lion_nodeid",
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_impassable_deep": sum(1 for e in edges if e["impassable_deep"]),
        "n_impassable_pond": sum(1 for e in edges if e["impassable_pond"]),
        "lion_gdb": str(gdb),
    }


def build_exposure_graph(
    *,
    gpkg,
    depth_tif,
    node_quant: float = DEFAULT_NODE_QUANT,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Fallback graph from sparse exposure GPKG roads (+ densify + soft connectors)."""
    highway_keep = {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "residential",
        "unclassified",
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }
    gdf = gpd.read_file(gpkg, layer=LAYER_ROADS)
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        gdf = gdf.cx[minx:maxx, miny:maxy]
    nodes: dict[tuple[float, float], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    with rasterio.open(depth_tif) as ds:
        for idx, row in gdf.iterrows():
            hwy = str(row.get("highway") or "").lower()
            if hwy and hwy not in highway_keep:
                continue
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
            if geom.geom_type not in ("LineString", "MultiLineString"):
                continue
            depth, _off = _sample_depth(ds, geom, LAYER_ROADS)
            depth_m = float(depth) if np.isfinite(depth) else 0.0
            aid = _asset_id(row, LAYER_ROADS, int(idx) if isinstance(idx, (int, np.integer)) else len(edges))
            name = _asset_name(row, LAYER_ROADS, int(idx) if isinstance(idx, (int, np.integer)) else 0)
            for part_i, part in enumerate(parts):
                coords = _densify_coords([(float(x), float(y)) for x, y, *_ in part.coords])
                qcoords = [_quantize(x, y, node_quant) for x, y in coords]
                compact: list[tuple[float, float]] = []
                for c in qcoords:
                    if not compact or c != compact[-1]:
                        compact.append(c)
                if len(compact) < 2:
                    continue
                for n in compact:
                    if n not in nodes:
                        nodes[n] = {"id": f"n:{n[0]:.5f}:{n[1]:.5f}", "lon": n[0], "lat": n[1]}
                for seg_i, (u, v) in enumerate(zip(compact, compact[1:])):
                    edges.append(
                        {
                            "id": f"{aid}#{part_i}:{seg_i}",
                            "road_id": aid,
                            "name": name,
                            "highway": hwy,
                            "u": nodes[u]["id"],
                            "v": nodes[v]["id"],
                            "length_m": round(max(_haversine_m(u, v), 1.0), 1),
                            "depth_m": round(depth_m, 4),
                            "depth_cm": round(depth_m * 100.0, 1),
                            "impassable_deep": depth_m >= DEEP_M,
                            "impassable_pond": depth_m >= POND_M,
                            "geometry": mapping(LineString([u, v])),
                            "source": "exposure_gpkg",
                        }
                    )
    # Soft connectors between nearby component tips (research topology glue)
    node_list = list(nodes.values())
    by_id = {n["id"]: n for n in node_list}
    join_n = 0
    for i, a in enumerate(node_list):
        for b in node_list[i + 1 :]:
            d = _haversine_m((a["lon"], a["lat"]), (b["lon"], b["lat"]))
            if 1.0 < d <= 140.0:
                edges.append(
                    {
                        "id": f"connector:{a['id']}:{b['id']}",
                        "road_id": "synthetic_connector",
                        "name": "Research topology connector",
                        "highway": "connector",
                        "u": a["id"],
                        "v": b["id"],
                        "length_m": round(d, 1),
                        "depth_m": 0.0,
                        "depth_cm": 0.0,
                        "impassable_deep": False,
                        "impassable_pond": False,
                        "geometry": mapping(
                            LineString([(a["lon"], a["lat"]), (b["lon"], b["lat"])])
                        ),
                        "source": "synthetic_connector",
                        "synthetic": True,
                    }
                )
                join_n += 1
                if join_n > 4000:
                    break
        if join_n > 4000:
            break
    return {
        "nodes": list(by_id.values()),
        "edges": edges,
        "topology": "exposure_densify_plus_connectors",
        "n_nodes": len(by_id),
        "n_edges": len(edges),
        "n_impassable_deep": sum(1 for e in edges if e["impassable_deep"]),
        "n_impassable_pond": sum(1 for e in edges if e["impassable_pond"]),
        "n_synthetic_connectors": join_n,
    }


def build_road_graph(
    *,
    gpkg,
    depth_tif,
    node_quant: float = DEFAULT_NODE_QUANT,
    bbox: tuple[float, float, float, float] | None = None,
    highway_keep: set[str] | None = None,  # noqa: ARG001 — kept for API compat
    prefer_lion: bool = True,
    lion_gdb: Path | None = None,
) -> dict[str, Any]:
    if prefer_lion and bbox is not None:
        lion = build_lion_graph(depth_tif=depth_tif, bbox=bbox, lion_gdb=lion_gdb)
        if lion is not None:
            return lion
    return build_exposure_graph(
        gpkg=gpkg, depth_tif=depth_tif, node_quant=node_quant, bbox=bbox
    )


def _nearest_node(nodes: list[dict[str, Any]], lon: float, lat: float) -> str | None:
    if not nodes:
        return None
    best = None
    best_d = float("inf")
    for n in nodes:
        d = _haversine_m((lon, lat), (n["lon"], n["lat"]))
        if d < best_d:
            best_d = d
            best = n["id"]
    return best


def _adj(
    edges: list[dict[str, Any]], *, block_deep: bool, block_pond: bool
) -> dict[str, list[tuple[str, float, dict]]]:
    adj: dict[str, list[tuple[str, float, dict]]] = {}
    for e in edges:
        if block_deep and e["impassable_deep"]:
            continue
        if block_pond and e["impassable_pond"]:
            continue
        w = float(e["length_m"])
        adj.setdefault(e["u"], []).append((e["v"], w, e))
        adj.setdefault(e["v"], []).append((e["u"], w, e))
    return adj


def dijkstra(
    adj: dict[str, list[tuple[str, float, dict]]],
    source: str,
    target: str,
) -> dict[str, Any]:
    if source not in adj or target not in adj:
        return {"reachable": False, "length_m": None, "n_hops": 0, "edge_ids": [], "path_nodes": []}
    dist = {source: 0.0}
    prev: dict[str, tuple[str, dict] | None] = {source: None}
    heap = [(0.0, source)]
    seen: set[str] = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if u == target:
            break
        for v, w, e in adj.get(u, []):
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                prev[v] = (u, e)
                heapq.heappush(heap, (nd, v))
    if target not in prev and target != source:
        return {"reachable": False, "length_m": None, "n_hops": 0, "edge_ids": [], "path_nodes": []}
    path_nodes = [target]
    edge_ids: list[str] = []
    cur = target
    while cur != source:
        step = prev.get(cur)
        if step is None:
            return {"reachable": False, "length_m": None, "n_hops": 0, "edge_ids": [], "path_nodes": []}
        u, e = step
        edge_ids.append(e["id"])
        path_nodes.append(u)
        cur = u
    path_nodes.reverse()
    edge_ids.reverse()
    return {
        "reachable": True,
        "length_m": round(float(dist[target]), 1),
        "n_hops": len(edge_ids),
        "edge_ids": edge_ids,
        "path_nodes": path_nodes,
    }


def corridor_queries(
    graph: dict[str, Any],
    landmarks: list[Landmark],
) -> list[dict[str, Any]]:
    nodes = graph["nodes"]
    edges = graph["edges"]
    landmark_nodes = []
    for lm in landmarks:
        nid = _nearest_node(nodes, lm.lon, lm.lat)
        snap_m = None
        if nid:
            n = next(x for x in nodes if x["id"] == nid)
            snap_m = round(_haversine_m((lm.lon, lm.lat), (n["lon"], n["lat"])), 1)
        landmark_nodes.append({**lm.__dict__, "node_id": nid, "snap_m": snap_m})

    adj_open = _adj(edges, block_deep=False, block_pond=False)
    adj_avoid_deep = _adj(edges, block_deep=True, block_pond=False)
    adj_avoid_pond = _adj(edges, block_deep=True, block_pond=True)

    pairs = []
    for i in range(len(landmark_nodes)):
        for j in range(i + 1, len(landmark_nodes)):
            a, b = landmark_nodes[i], landmark_nodes[j]
            if not a["node_id"] or not b["node_id"]:
                pairs.append(
                    {
                        "from_id": a["id"],
                        "from_name": a["name"],
                        "to_id": b["id"],
                        "to_name": b["name"],
                        "status": "unsnapped",
                        "honesty": "Landmark could not snap to road graph.",
                    }
                )
                continue
            open_path = dijkstra(adj_open, a["node_id"], b["node_id"])
            avoid_deep = dijkstra(adj_avoid_deep, a["node_id"], b["node_id"])
            avoid_pond = dijkstra(adj_avoid_pond, a["node_id"], b["node_id"])
            if not open_path["reachable"]:
                status = "no_network_path"
            elif not avoid_deep["reachable"]:
                status = "cut_at_deep_ponding"
            elif not avoid_pond["reachable"]:
                status = "cut_at_ponding"
            elif (
                avoid_deep["length_m"]
                and open_path["length_m"]
                and avoid_deep["length_m"] > open_path["length_m"] * 1.25
            ):
                status = "detour_around_deep"
            else:
                status = "open_research"
            pairs.append(
                {
                    "from_id": a["id"],
                    "from_name": a["name"],
                    "to_id": b["id"],
                    "to_name": b["name"],
                    "from_snap_m": a["snap_m"],
                    "to_snap_m": b["snap_m"],
                    "status": status,
                    "open_path": open_path,
                    "avoid_deep_path": avoid_deep,
                    "avoid_pond_path": avoid_pond,
                    "delta_m_vs_open": (
                        None
                        if not (avoid_deep["reachable"] and open_path["reachable"])
                        else round(float(avoid_deep["length_m"]) - float(open_path["length_m"]), 1)
                    ),
                    "honesty": (
                        "Research impassability from HAND≥8 cm edge removal — "
                        "NOT an official DOT closure / NOT routing guidance."
                    ),
                }
            )
    return pairs


def path_feature_collection(graph: dict[str, Any], edge_ids: list[str]) -> dict[str, Any]:
    by_id = {e["id"]: e for e in graph["edges"]}
    feats = []
    for eid in edge_ids:
        e = by_id.get(eid)
        if not e:
            continue
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "id": e["id"],
                    "name": e["name"],
                    "depth_cm": e["depth_cm"],
                    "impassable_deep": e["impassable_deep"],
                    "length_m": e["length_m"],
                    "source": e.get("source"),
                },
                "geometry": e["geometry"],
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def build_corridor_payload(
    *,
    gpkg,
    depth_tif,
    landmarks: list[Landmark] | None = None,
    bbox_pad_deg: float = 0.045,
    lion_gdb: Path | None = None,
) -> dict[str, Any]:
    landmarks = landmarks or default_ida_landmarks()
    lons = [lm.lon for lm in landmarks]
    lats = [lm.lat for lm in landmarks]
    bbox = (
        min(lons) - bbox_pad_deg,
        min(lats) - bbox_pad_deg,
        max(lons) + bbox_pad_deg,
        max(lats) + bbox_pad_deg,
    )
    graph = build_road_graph(
        gpkg=gpkg, depth_tif=depth_tif, bbox=bbox, prefer_lion=True, lion_gdb=lion_gdb
    )
    pairs = corridor_queries(graph, landmarks)
    wet_edges = [e for e in graph["edges"] if e["impassable_deep"] or e["impassable_pond"]]
    corridors_geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": e["id"],
                    "name": e["name"],
                    "depth_cm": e["depth_cm"],
                    "impassable_deep": e["impassable_deep"],
                    "impassable_pond": e["impassable_pond"],
                    "highway": e.get("highway"),
                    "source": e.get("source"),
                },
                "geometry": e["geometry"],
            }
            for e in wet_edges
        ],
    }
    path_geos = {}
    for p in pairs:
        key = f"{p.get('from_id')}__{p.get('to_id')}"
        edge_ids = (
            (p.get("avoid_deep_path") or {}).get("edge_ids")
            or (p.get("open_path") or {}).get("edge_ids")
            or []
        )
        path_geos[key] = path_feature_collection(graph, edge_ids)

    return {
        "product": "corridor_impassability_research",
        "official_nws": False,
        "decision_grade": False,
        "official_closures": False,
        "honesty": (
            "Research corridor impassability graph: wet HAND road edges (≥3 / ≥8 cm) "
            "removed to test landmark connectivity on LION/OSM topology. "
            "NOT official DOT closures / NOT navigation."
        ),
        "event_id": "ida-2021",
        "thresholds_m": {"ponding": POND_M, "deep_ponding": DEEP_M},
        "bbox": bbox,
        "topology": graph.get("topology"),
        "graph_stats": {
            "n_nodes": graph["n_nodes"],
            "n_edges": graph["n_edges"],
            "n_impassable_deep": graph["n_impassable_deep"],
            "n_impassable_pond": graph["n_impassable_pond"],
            "topology": graph.get("topology"),
        },
        "landmarks": [lm.__dict__ for lm in landmarks],
        "pairs": pairs,
        "wet_edges_geojson": "corridor_wet_edges.geojson",
        "paths_geojson": "corridor_research_paths.geojson",
        "corridors_geo": corridors_geo,
        "path_geos": path_geos,
    }
