"""Open drainage / sewer *capacity proxy* (research screening).

NOT a DEP sewer model, NOT SWMM, NOT a reconstructed pipe network.
Uses open proxies only:

- NLCD impervious fraction (land-cover demand / residual infiltration assist)
- Optional catch-basin / drain-node density when open points exist (OSM / NYC open data)
- Literature-anchored design capacity as a mm/hr *sink* that reduces effective precip
  before HAND/bathtub (and optionally SFINCS precip rates)

Extreme-event surcharge: when storm intensity ≫ design capacity, inlet/system
efficiency collapses so more excess remains (Ida-like overload), rather than
naively removing capacity×duration forever.

References (order-of-magnitude anchors, not NYC calibration certificates):
- Urban drainage design intensities often ~25–45 mm/hr for short-duration storms;
  sustained multi-hour conveyance under surcharge is lower.
- Pluvial screening / "blue spot" style methods commonly apply a constant or
  land-cover-modulated drainage rate sink (~5–25 mm/hr).
- Butler & Davies, *Urban Drainage*; US EPA SWMM conceptual storage analogies.

Research only — NOT official NWS / NOT decision-grade / NOT DEP-approved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio import features as rio_features
from rasterio.enums import Resampling
from rasterio.warp import reproject
from shapely.geometry import Point

# --- Literature-anchored knobs (documented; loosely checkable vs Ida/311) ---
# Sustained multi-hour capacity under load (not peak 5-min design intensity).
CAP_BASE_MM_HR = 10.0  # low inlet density / older combined under sustained load
CAP_MAX_MM_HR = 22.0  # ~0.9 in/hr when open drain points support higher capacity
ALPHA_IMPERVIOUS = 0.35  # high pavement → less residual infiltration assist
SURCHARGE_K = 0.85  # efficiency collapse when intensity > capacity
DEFAULT_EVENT_DURATION_HR = 12.0  # Ida event window for mean intensity / SFINCS
# Critical: sewers do NOT remove design_rate × full event duration everywhere.
# Screening uses a shorter effective drainage window (peak flash hours) so Ida
# storm-totals retain excess where intensity overwhelms conveyance — otherwise
# capacity×12h (~120 mm) falsely drains most of the city.
EFFECTIVE_DRAINAGE_HOURS = 3.0
DRAIN_BUFFER_DEG = 0.0015  # ~150 m inlet influence for density raster
ENGINE_ID = "drainage_capacity_proxy_v1"
ENGINE_LABEL = "Open drainage capacity proxy (NLCD + optional drain density + mm/hr sink)"


def load_impervious_fraction(
    shape: tuple[int, int],
    transform,
    crs,
    impervious_path: Path,
) -> np.ndarray:
    """Warp NLCD (0–100 or 0–1) to target grid as fraction in [0, 1]."""
    out = np.zeros(shape, dtype=np.float32)
    with rasterio.open(impervious_path) as src:
        src_data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            src_data = np.where(src_data == src.nodata, np.nan, src_data)
        # NLCD ISA sometimes uses 127 as nodata/fill
        src_data = np.where(src_data > 100, np.nan, src_data)
        reproject(
            source=src_data,
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=0.0,
        )
    finite = np.isfinite(out)
    if finite.any() and float(np.nanmax(out[finite])) > 1.5:
        out = np.clip(out / 100.0, 0, 1)
    else:
        out = np.clip(np.nan_to_num(out, nan=0.0), 0, 1)
    return out.astype(np.float32)


def _accept_drain_props(props: dict | None) -> bool:
    """Keep real open points; reject synthetic demo graph nodes."""
    props = props or {}
    if props.get("synthetic") is True:
        return False
    source = str(props.get("source") or "").lower()
    # Explicit OSM / NYC Open Data catch-basin / inlet points are OK.
    if (
        source.startswith("osm")
        or source.startswith("nyc_open_data")
        or source.startswith("nycdep")
        or "manhole" in source
        or "inlet" in source
        or "catch_basin" in source
    ):
        # Still reject synthetic demo graph placeholders named basin_N.
        node_id = str(props.get("node_id") or "")
        if props.get("synthetic") is True or (
            props.get("demo_only") is True and node_id.startswith("basin_")
        ):
            return False
        return True
    # Reject remaining demo catchment-graph nodes (road-derived placeholders).
    if props.get("demo_only") is True and "catch_basin" in str(props.get("kind", "")).lower():
        return False
    return True


def _points_from_payload(raw: Any) -> list[Point]:
    """Extract accepted drain points from GeoJSON / Overpass / SODA payloads."""
    if isinstance(raw, dict) and raw.get("errorCode"):
        return []
    pts: list[Point] = []
    feats = raw.get("features") if isinstance(raw, dict) else None
    if feats is None and isinstance(raw, list):
        # NYC SODA row list with the_geom / lat-lon
        for row in raw:
            if not isinstance(row, dict):
                continue
            if not _accept_drain_props(row):
                continue
            geom = row.get("the_geom")
            if isinstance(geom, dict) and geom.get("type") == "Point":
                lon, lat = geom["coordinates"][:2]
                pts.append(Point(float(lon), float(lat)))
            elif row.get("longitude") is not None and row.get("latitude") is not None:
                pts.append(Point(float(row["longitude"]), float(row["latitude"])))
        return pts
    if feats is None and isinstance(raw, dict) and "elements" in raw:
        for el in raw["elements"]:
            if "lat" in el and "lon" in el:
                pts.append(Point(float(el["lon"]), float(el["lat"])))
        return pts
    for feat in feats or []:
        if not _accept_drain_props(feat.get("properties")):
            continue
        geom = feat.get("geometry") or {}
        if geom.get("type") == "Point":
            lon, lat = geom["coordinates"][:2]
            pts.append(Point(float(lon), float(lat)))
        elif geom.get("type") == "MultiPoint":
            for lon, lat, *_ in geom["coordinates"]:
                pts.append(Point(float(lon), float(lat)))
    return pts


def default_drain_candidate_paths(raw_dir: Path, *extra_roots: Path) -> list[Path]:
    """Prefer metro-wide OSM inventory, then Queens, then catch-basin caches / DEP SODA."""
    roots = [raw_dir, *extra_roots]
    ordered: list[Path] = []
    names = (
        "osm_drains_metro.geojson",
        "osm_drains_south_queens.geojson",
        "catch_basins.geojson",
        "nycdep_catch_basins_metro.json",
        "nycdep_catch_basins_south_queens.json",
    )
    for name in names:
        for root in roots:
            candidate = root / name
            if candidate not in ordered:
                ordered.append(candidate)
            infra = root / "infrastructure" / name
            if infra not in ordered:
                ordered.append(infra)
            ida = root / "ida_v0_assets" / name
            if ida not in ordered:
                ordered.append(ida)
    return ordered


def load_drain_points(
    paths: list[Path],
    *,
    merge: bool = True,
) -> tuple[list[Point], Path | None, str]:
    """Load open drain / catch-basin points; skip SODA errors and synthetic demo nodes.

    When ``merge`` is True (default), union points across all readable open inventories
    so metro OSM densification is not shadowed by a thinner Queens-only file earlier
    in the candidate list. Returns the highest-priority path that contributed points.
    """
    merged: list[Point] = []
    seen: set[tuple[float, float]] = set()
    primary_path: Path | None = None
    for path in paths:
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        pts = _points_from_payload(raw)
        if not pts:
            continue
        if primary_path is None:
            primary_path = path
        if not merge:
            return pts, path, "open_points"
        for p in pts:
            key = (round(p.x, 6), round(p.y, 6))
            if key in seen:
                continue
            seen.add(key)
            merged.append(p)
    if merged:
        return merged, primary_path, "open_points"
    return [], None, "missing"


def drain_coverage_fraction(
    drain_norm: np.ndarray,
    land: np.ndarray | None = None,
) -> dict[str, float | int]:
    """Honest coverage: share of land (or all) cells with any inlet-density credit."""
    mask = np.ones(drain_norm.shape, dtype=bool) if land is None else land.astype(bool)
    n = int(mask.sum())
    if n == 0:
        return {"n_land": 0, "n_with_drain_credit": 0, "fraction_with_drain_credit": 0.0}
    credited = int(((drain_norm > 0) & mask).sum())
    return {
        "n_land": n,
        "n_with_drain_credit": credited,
        "fraction_with_drain_credit": float(credited / n),
    }


def drain_density_norm(
    shape: tuple[int, int],
    transform,
    points: list[Point],
    *,
    buffer_deg: float = DRAIN_BUFFER_DEG,
) -> np.ndarray:
    """Normalized inlet density in [0, 1]; zeros when no open points (no false credit)."""
    dens = np.zeros(shape, dtype=np.float32)
    if not points:
        return dens
    shapes = [(p.buffer(buffer_deg), 1.0) for p in points]
    burned = rio_features.rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0.0,
        dtype=np.float32,
    )
    if burned.max() > 0:
        dens = (burned / float(burned.max())).astype(np.float32)
    return dens


def capacity_mm_hr(
    impervious: np.ndarray,
    drain_norm: np.ndarray,
    *,
    cap_base: float = CAP_BASE_MM_HR,
    cap_max: float = CAP_MAX_MM_HR,
    alpha_imp: float = ALPHA_IMPERVIOUS,
) -> np.ndarray:
    """Spatial design-capacity field [mm/hr]."""
    imp = np.clip(np.nan_to_num(impervious, nan=0.0), 0, 1)
    drain = np.clip(np.nan_to_num(drain_norm, nan=0.0), 0, 1)
    cap = cap_base + (cap_max - cap_base) * drain
    cap = cap * (1.0 - alpha_imp * imp)
    return np.clip(cap, 0.0, cap_max).astype(np.float32)


def effective_sink_mm(
    precip_mm: np.ndarray,
    capacity: np.ndarray,
    *,
    duration_hr: float = DEFAULT_EVENT_DURATION_HR,
    drainage_hours: float = EFFECTIVE_DRAINAGE_HOURS,
    surcharge_k: float = SURCHARGE_K,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (effective_sink_mm, excess_precip_mm, efficiency).

    Mean intensity = precip / event duration (for surcharge). Removable volume =
    capacity × effective_drainage_hours × efficiency — not capacity × full event
    length (which would over-drain Ida storm-totals).
    """
    precip = np.clip(np.nan_to_num(precip_mm, nan=0.0), 0, None).astype(np.float64)
    cap = np.clip(np.nan_to_num(capacity, nan=0.0), 0, None).astype(np.float64)
    duration = max(float(duration_hr), 1e-6)
    drain_h = max(float(drainage_hours), 1e-6)
    intensity = precip / duration
    # utilization > 1 → surcharge; efficiency = 1 / (1 + k*(u-1)^2)
    util = np.where(cap > 1e-6, intensity / cap, np.inf)
    over = np.clip(util - 1.0, 0, None)
    efficiency = 1.0 / (1.0 + surcharge_k * over * over)
    efficiency = np.where(np.isfinite(efficiency), efficiency, 0.0)
    sink = np.minimum(precip, cap * drain_h * efficiency)
    excess = np.clip(precip - sink, 0, None)
    return sink.astype(np.float32), excess.astype(np.float32), efficiency.astype(np.float32)


def apply_capacity_to_rate_mm_hr(
    rate_mm_hr: np.ndarray,
    capacity: np.ndarray,
    *,
    event_duration_hr: float = DEFAULT_EVENT_DURATION_HR,
    drainage_hours: float = EFFECTIVE_DRAINAGE_HOURS,
    surcharge_k: float = SURCHARGE_K,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce precip *rate* for SFINCS to match storm-total sink volume.

    Continuous sink rate is scaled by effective_drainage_hours / event_duration so
    a 12 h SFINCS run does not remove capacity×12 h (over-drain).
    """
    rate = np.clip(np.nan_to_num(rate_mm_hr, nan=0.0), 0, None).astype(np.float64)
    cap = np.clip(np.nan_to_num(capacity, nan=0.0), 0, None).astype(np.float64)
    scale = max(float(drainage_hours), 0.0) / max(float(event_duration_hr), 1e-6)
    util = np.where(cap > 1e-6, rate / cap, np.inf)
    over = np.clip(util - 1.0, 0, None)
    efficiency = 1.0 / (1.0 + surcharge_k * over * over)
    efficiency = np.where(np.isfinite(efficiency), efficiency, 0.0)
    sink_rate = np.minimum(rate, cap * scale * efficiency)
    excess_rate = np.clip(rate - sink_rate, 0, None)
    return excess_rate.astype(np.float32), efficiency.astype(np.float32)


def param_meta() -> dict[str, Any]:
    return {
        "engine": ENGINE_ID,
        "label": ENGINE_LABEL,
        "cap_base_mm_hr": CAP_BASE_MM_HR,
        "cap_max_mm_hr": CAP_MAX_MM_HR,
        "alpha_impervious": ALPHA_IMPERVIOUS,
        "surcharge_k": SURCHARGE_K,
        "default_event_duration_hr": DEFAULT_EVENT_DURATION_HR,
        "effective_drainage_hours": EFFECTIVE_DRAINAGE_HOURS,
        "drain_buffer_deg": DRAIN_BUFFER_DEG,
        "formula": (
            "capacity_mm_hr = (CAP_BASE + (CAP_MAX-CAP_BASE)*drain_norm) * (1 - α·impervious); "
            "intensity = precip/event_duration; "
            "efficiency = 1/(1 + k·max(0, intensity/capacity - 1)²); "
            "excess_precip_mm = precip_mm - min(precip, capacity·effective_drainage_hours·efficiency)"
        ),
        "not_dep_sewer": True,
        "not_swmm": True,
        "official_nws": False,
        "decision_grade": False,
        "citations_note": (
            "Order-of-magnitude urban drainage design / pluvial screening sink rates "
            "(~5–25 mm/hr sustained; short-duration design often higher). "
            "Effective drainage hours ≪ full event length so storm-total screening does not "
            "over-credit conveyance. Not a calibrated NYC DEP network."
        ),
    }
