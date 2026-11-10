#!/usr/bin/env python3
"""Multi-factor flood susceptibility screening (weather × landscape × infrastructure).

Produces static factor layers + helpers used by the Earth2 radar stack.
Screening index only — not inundation depth or calibrated flood probability.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio import features as rio_features
from rasterio.transform import from_bounds
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROCESSED_DIR, RAW_DIR
from nyc_flash_flood_case_study.extents import EXTENTS
from nyc_flash_flood_case_study.pluvial import (
    _find_dem,
    _find_impervious,
    _osm_highways_path,
    _warp_to_grid,
    build_built_surface_fraction,
    build_terrain_screening_from_dem,
)

ASSETS = FIGURES_DIR / "product_assets"
FACTOR_DIR = PROCESSED_DIR / "susceptibility_factors"
EXTENT_ID = "citywide"
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]

# Documented screening weights (see science-and-polish-roadmap.md)
WEIGHTS = {
    "weather": 0.35,
    "landscape": 0.40,
    "infra": 0.15,
    "interaction_weather_landscape": 0.10,
    "landscape_terrain": 0.55,
    "landscape_impervious": 0.45,
    "infra_built": 0.70,
    "infra_drain_deficit": 0.30,
}

FORMULA = (
    "S = clip(0.35*weather + 0.40*landscape + 0.15*infra + 0.10*weather*landscape, 0, 1); "
    "landscape = 0.55*terrain_lowflat + 0.45*impervious; "
    "infra = 0.70*built_road_proxy + 0.30*(1 - drain_density_norm)"
)


def _display_shape() -> tuple[int, int]:
    dem = _find_dem()
    if dem is not None:
        with rasterio.open(dem) as src:
            res = max(abs(src.res[0]), abs(src.res[1])) * 3.0
            width = max(200, int(round((BOUNDS["xmax"] - BOUNDS["xmin"]) / res)))
            height = max(120, int(round((BOUNDS["ymax"] - BOUNDS["ymin"]) / res)))
            return height, width
    return (360, 480)


def _drain_density(shape_hw: tuple[int, int], transform) -> np.ndarray:
    """Normalized catch-basin / drain node density; missing → zeros (no false drainage credit)."""
    h, w = shape_hw
    dens = np.zeros((h, w), dtype=np.float32)
    candidates = [
        ASSETS / "drainage_nodes.geojson",
        RAW_DIR / "infrastructure" / "osm_drains_south_queens.geojson",
    ]
    pts = []
    for path in candidates:
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        if raw.get("errorCode"):
            continue
        for feat in raw.get("features") or []:
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Point":
                lon, lat = geom["coordinates"][:2]
                pts.append(Point(lon, lat))
        if pts:
            break
    if not pts:
        return dens
    # Rasterize point counts into coarse cells then normalize
    shapes = [(p.buffer(0.0015), 1) for p in pts]  # ~150 m influence
    burned = rio_features.rasterize(
        shapes,
        out_shape=(h, w),
        transform=transform,
        fill=0,
        dtype=np.float32,
    )
    if burned.max() > 0:
        dens = burned / float(burned.max())
    return dens


def build_static_factors(display_shape: tuple[int, int] | None = None) -> dict:
    FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    h, w = display_shape or _display_shape()
    transform = from_bounds(BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"], w, h)

    # Ensure terrain screening exists for citywide DEM
    dem = _find_dem()
    terrain_path = PROCESSED_DIR / "terrain_screening_citywide.tif"
    if dem is not None and "citywide" in dem.name and not terrain_path.exists():
        build_terrain_screening_from_dem(dem, terrain_path)
    if not terrain_path.exists():
        # fall back to whatever pluvial finder would use
        from nyc_flash_flood_case_study.pluvial import _find_terrain_screening

        tp = _find_terrain_screening()
        if tp:
            terrain_path = tp

    terrain = np.zeros((h, w), dtype=np.float32)
    impervious = np.zeros((h, w), dtype=np.float32)
    sources: list[str] = []

    if terrain_path.exists():
        _warp_to_grid(terrain_path, terrain, transform)
        sources.append(str(terrain_path))
        finite = np.isfinite(terrain)
        if finite.any():
            tmin, tmax = float(np.nanmin(terrain[finite])), float(np.nanmax(terrain[finite]))
            terrain = np.clip((terrain - tmin) / max(tmax - tmin, 1e-6), 0, 1)

    imp_path = _find_impervious()
    if imp_path is not None:
        _warp_to_grid(imp_path, impervious, transform)
        sources.append(str(imp_path))
        finite = np.isfinite(impervious)
        if finite.any() and float(np.nanmax(impervious[finite])) > 1.5:
            impervious = np.clip(impervious / 100.0, 0, 1)
        else:
            impervious = np.clip(impervious, 0, 1)

    built_tif = FACTOR_DIR / "built_road_proxy.tif"
    built, built_meta = build_built_surface_fraction(BOUNDS, h, w, transform, out_tif=built_tif)
    if built_meta.get("source"):
        sources.append(built_meta["source"])

    drain = _drain_density((h, w), transform)
    landscape = np.clip(
        WEIGHTS["landscape_terrain"] * terrain + WEIGHTS["landscape_impervious"] * impervious, 0, 1
    ).astype(np.float32)
    infra = np.clip(
        WEIGHTS["infra_built"] * built + WEIGHTS["infra_drain_deficit"] * (1.0 - drain), 0, 1
    ).astype(np.float32)

    def _write(name: str, data: np.ndarray) -> Path:
        path = FACTOR_DIR / name
        profile = {
            "driver": "GTiff",
            "height": h,
            "width": w,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": -9999.0,
            "compress": "deflate",
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(data), data, -9999.0), 1)
        return path

    paths = {
        "terrain": str(_write("factor_terrain.tif", terrain)),
        "impervious": str(_write("factor_impervious.tif", impervious)),
        "landscape": str(_write("factor_landscape.tif", landscape)),
        "built": str(_write("factor_built.tif", built)),
        "drain_density": str(_write("factor_drain_density.tif", drain)),
        "infra": str(_write("factor_infra.tif", infra)),
    }

    meta = {
        "label": "Multi-factor susceptibility factors",
        "disclaimer": (
            "Relative screening from weather × landscape × infrastructure. "
            "Not inundation depth, not flood probability, not a calibrated hydrology model."
        ),
        "formula": FORMULA,
        "weights": WEIGHTS,
        "extent_id": EXTENT_ID,
        "shape": [h, w],
        "bounds": [[BOUNDS["ymin"], BOUNDS["xmin"]], [BOUNDS["ymax"], BOUNDS["xmax"]]],
        "transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        "paths": paths,
        "sources": sources,
        "citations_note": (
            "Compound flood-susceptibility indices commonly combine hazard intensity, "
            "land-surface predisposition (topography, imperviousness), and exposure/drainage; "
            "weights here are transparent screening defaults, not NYC-calibrated parameters."
        ),
    }
    (FACTOR_DIR / "factors_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "susceptibility_factors_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def combine_frame(landscape: np.ndarray, infra: np.ndarray, precip_norm: np.ndarray) -> np.ndarray:
    weather = np.clip(precip_norm, 0, 1)
    s = (
        WEIGHTS["weather"] * weather
        + WEIGHTS["landscape"] * landscape
        + WEIGHTS["infra"] * infra
        + WEIGHTS["interaction_weather_landscape"] * weather * landscape
    )
    return np.clip(s, 0, 1).astype(np.float32)


if __name__ == "__main__":
    print(json.dumps(build_static_factors(), indent=2)[:1200])
