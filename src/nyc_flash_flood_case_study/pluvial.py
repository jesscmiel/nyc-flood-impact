"""Pluvial flood screening from terrain + built surface (not inundation depth)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio import features as rio_features
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from shapely.geometry import LineString, mapping

from .config import EVENT_OUTPUTS, FIGURES_DIR, LANDCOVER_DATASETS, PROCESSED_DIR, PROJECT_ROOT, RAW_DIR
from .extents import EXTENTS


def _find_impervious() -> Path | None:
    # Prefer real NLCD percent-impervious clips over any demo placeholder.
    candidates = [
        PROJECT_ROOT / "data" / "raw" / "landcover" / "nlcd_2021_impervious_south_queens.tif",
        PROJECT_ROOT / "data" / "raw" / "landcover" / "nlcd_2021_impervious_citywide.tif",
        LANDCOVER_DATASETS["impervious"],
        PROJECT_ROOT / "legacy_projects_data" / "raw" / "landcover" / "impervious_surface.tif",
        PROJECT_ROOT / "data" / "raw" / "landcover" / "impervious_surface.tif",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _find_terrain_screening() -> Path | None:
    candidates = [
        EVENT_OUTPUTS["terrain_screening_highres"],
        PROCESSED_DIR / "terrain_screening_10m.tif",
        PROJECT_ROOT / "legacy_projects_data" / "processed" / "flash_flood_susceptibility.tif",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _find_dem() -> Path | None:
    candidates = [
        RAW_DIR / "terrain" / "dem_usgs_1_3_arcsec.tif",
        EVENT_OUTPUTS.get("dem_highres", RAW_DIR / "terrain" / "dem_usgs_1_3_arcsec.tif"),
        RAW_DIR / "terrain" / "dem.tif",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return Path(path)
    return None


def _is_demo_impervious(path: Path) -> bool:
    """Heuristic: synthetic demo rasters are near-constant or tiny grids."""
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        if src.width * src.height < 50_000 and float(np.ma.std(data)) < 0.08:
            return True
        # Constant / near-constant field
        if data.count() and float(np.ma.std(data)) < 1e-3:
            return True
    return False


def _osm_highways_path() -> Path | None:
    candidates = [
        RAW_DIR / "infrastructure" / "osm_highways_south_queens.json",
        FIGURES_DIR / "product_assets" / "roads.geojson",
        FIGURES_DIR / "ida_v0_assets" / "roads.geojson",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _lines_from_osm_highways(path: Path) -> list:
    raw = json.loads(path.read_text())
    lines = []
    if path.suffix == ".geojson" or (isinstance(raw, dict) and raw.get("type") == "FeatureCollection"):
        for feat in raw.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") == "LineString":
                coords = [(c[0], c[1]) for c in geom["coordinates"]]
                if len(coords) >= 2:
                    lines.append(LineString(coords))
            elif geom.get("type") == "MultiLineString":
                for part in geom["coordinates"]:
                    coords = [(c[0], c[1]) for c in part]
                    if len(coords) >= 2:
                        lines.append(LineString(coords))
        return lines

    for el in raw.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        lines.append(LineString(coords))
    return lines


def build_built_surface_fraction(
    bounds: dict,
    height: int,
    width: int,
    transform,
    out_tif: Path | None = None,
) -> tuple[np.ndarray, dict]:
    """Rasterize OSM/road centerlines into a relative built-surface fraction.

    This is a **proxy** for imperviousness (road corridors), not NLCD percent
    impervious and not building footprints. Honest screening input only.
    """
    meta = {
        "source": None,
        "n_lines": 0,
        "kind": "built_surface_proxy_roads",
        "note": (
            "Road-centerline density proxy for built/impervious surface. "
            "Not NLCD percent impervious; not building footprints."
        ),
    }
    grid = np.zeros((height, width), dtype=np.float32)
    path = _osm_highways_path()
    if path is None:
        meta["note"] = "No OSM/road geometry found; built fraction left at 0."
        return grid, meta

    lines = _lines_from_osm_highways(path)
    meta["source"] = str(path)
    meta["n_lines"] = len(lines)
    if not lines:
        return grid, meta

    shapes = ((mapping(line), 1.0) for line in lines)
    burned = rio_features.rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0.0,
        dtype="float32",
        all_touched=True,
    )
    # Soften centerlines into a neighborhood fraction (approx street corridor).
    from scipy.ndimage import uniform_filter

    soft = uniform_filter(burned.astype(np.float32), size=5)
    if float(np.nanmax(soft)) > 0:
        soft = soft / float(np.nanmax(soft))
    grid = np.clip(soft, 0, 1).astype(np.float32)

    if out_tif is not None:
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": -9999.0,
            "compress": "deflate",
        }
        out_tif.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_tif, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(grid), grid, -9999.0), 1)
            dst.update_tags(**{k: str(v) for k, v in meta.items() if v is not None})
    return grid, meta


def _warp_to_grid(path: Path, destination: np.ndarray, transform, resampling=Resampling.bilinear) -> None:
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs or "EPSG:4326",
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=resampling,
        )


def build_pluvial_screening(
    extent_id: str = "south_queens",
    display_shape: tuple[int, int] | None = None,
    assets_dir: Path | None = None,
) -> dict:
    """Combine relative terrain screening with built/impervious surface into a pluvial index.

    Output is a **screening index** in [0, 1], not water depth or flood probability.
    Prefers USGS ~10 m terrain screening already on disk. Replaces demo/constant
    impervious rasters with an OSM road built-surface proxy when needed.
    """
    assets_dir = assets_dir or (FIGURES_DIR / "product_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    processed = PROCESSED_DIR / "pluvial"
    processed.mkdir(parents=True, exist_ok=True)

    bounds = EXTENTS[extent_id]["bounds"]

    # Prefer DEM-native ~10 m grid when available; else a denser display grid.
    dem_path = _find_dem()
    if display_shape is None and dem_path is not None:
        with rasterio.open(dem_path) as src:
            # Clip approx to extent via window math for shape, but write in EPSG:4326 display grid.
            # Use ~1/3 of DEM resolution in lon/lat degrees for manageable PNG (~30 m-ish).
            res = max(abs(src.res[0]), abs(src.res[1]))
            # ~3× DEM pixel for product display (~30 m) keeps files small.
            cell = res * 3.0
            width = max(200, int(round((bounds["xmax"] - bounds["xmin"]) / cell)))
            height = max(120, int(round((bounds["ymax"] - bounds["ymin"]) / cell)))
            display_shape = (height, width)
    if display_shape is None:
        display_shape = (220, 480)

    height, width = display_shape
    transform = from_bounds(
        bounds["xmin"], bounds["ymin"], bounds["xmax"], bounds["ymax"], width, height
    )

    terrain_path = _find_terrain_screening()
    impervious_path = _find_impervious()
    if terrain_path is None and impervious_path is None and _osm_highways_path() is None:
        raise FileNotFoundError("Need terrain screening and/or built/impervious inputs for pluvial screening.")

    terrain = np.zeros((height, width), dtype=np.float32)
    impervious = np.zeros((height, width), dtype=np.float32)
    sources: list[str] = []
    impervious_kind = "none"
    warnings: list[str] = []

    if terrain_path is not None:
        _warp_to_grid(terrain_path, terrain, transform)
        sources.append(str(terrain_path))
        finite = np.isfinite(terrain)
        if finite.any():
            tmin, tmax = float(np.nanmin(terrain[finite])), float(np.nanmax(terrain[finite]))
            terrain = np.clip((terrain - tmin) / max(tmax - tmin, 1e-6), 0, 1)

    use_demo_impervious = False
    if impervious_path is not None:
        use_demo_impervious = _is_demo_impervious(impervious_path)
        if use_demo_impervious:
            warnings.append(
                f"Detected demo/near-constant impervious raster ({impervious_path.name}); "
                "preferring OSM road built-surface proxy."
            )
        else:
            _warp_to_grid(impervious_path, impervious, transform)
            sources.append(str(impervious_path))
            impervious_kind = "nlcd_or_percent_impervious"
            finite = np.isfinite(impervious)
            if finite.any():
                vals = impervious[finite]
                if float(np.nanmax(vals)) > 1.5:
                    impervious = np.clip(impervious / 100.0, 0, 1)
                else:
                    impervious = np.clip(impervious, 0, 1)

    if impervious_kind == "none":
        built_tif = processed / f"built_surface_proxy_{extent_id}.tif"
        impervious, built_meta = build_built_surface_fraction(
            bounds, height, width, transform, out_tif=built_tif
        )
        if built_meta.get("source"):
            sources.append(built_meta["source"])
            impervious_kind = built_meta["kind"]
            warnings.append(built_meta["note"])
        else:
            warnings.append(built_meta.get("note") or "No built-surface proxy available.")

    # Pluvial screening: low/flat terrain + built/impervious favor street flooding risk.
    if impervious_kind.startswith("built_surface"):
        pluvial = np.clip(0.60 * terrain + 0.40 * impervious, 0, 1).astype(np.float32)
        formula = "0.60 * terrain_screening + 0.40 * built_surface_proxy_roads"
    else:
        pluvial = np.clip(0.55 * terrain + 0.45 * impervious, 0, 1).astype(np.float32)
        formula = "0.55 * terrain_screening + 0.45 * imperviousness"

    tif_path = processed / f"pluvial_screening_{extent_id}.tif"
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
        "compress": "deflate",
    }
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(pluvial), pluvial, -9999.0), 1)
        dst.update_tags(
            interpretation="Pluvial screening index only — not inundation depth.",
            formula=formula,
            impervious_kind=impervious_kind,
        )

    rgba = colormaps["YlOrRd"](pluvial, bytes=True)
    rgba[..., 3] = np.where(pluvial > 0.05, np.minimum(200, (60 + pluvial * 160)).astype(np.uint8), 0)
    png_path = assets_dir / "pluvial_screening.png"
    Image.fromarray(rgba, mode="RGBA").save(png_path, optimize=True)

    # Built-surface preview for product UI honesty.
    built_rgba = colormaps["Greys"](impervious, bytes=True)
    built_rgba[..., 3] = np.where(impervious > 0.05, np.minimum(180, (40 + impervious * 140)).astype(np.uint8), 0)
    built_png = assets_dir / "built_surface_proxy.png"
    Image.fromarray(built_rgba, mode="RGBA").save(built_png, optimize=True)

    meta = {
        "label": "Pluvial screening index",
        "disclaimer": (
            "Relative screening from terrain low/flatness and built/impervious surface only. "
            "Not inundation depth, not a flood warning, not a calibrated hydrology or SWMM model."
        ),
        "formula": formula,
        "png": png_path.name,
        "built_surface_png": built_png.name,
        "tif": str(tif_path),
        "extent_id": extent_id,
        "sources": sources,
        "impervious_kind": impervious_kind,
        "demo_impervious_rejected": use_demo_impervious,
        "warnings": warnings,
        "grid": {"height": height, "width": width, "approx_cell_deg": (bounds["xmax"] - bounds["xmin"]) / width},
        "bounds": [[bounds["ymin"], bounds["xmin"]], [bounds["ymax"], bounds["xmax"]]],
        "mean": float(np.nanmean(pluvial)),
        "p90": float(np.nanpercentile(pluvial, 90)),
    }
    (assets_dir / "pluvial_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


__all__ = ["build_pluvial_screening", "build_built_surface_fraction"]
