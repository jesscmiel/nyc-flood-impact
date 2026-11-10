#!/usr/bin/env python3
"""Clip product rasters/PNGs to Natural Earth land so overlays don't paint the harbor."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio import features as rio_features
from rasterio.transform import from_bounds

from nyc_flash_flood_case_study.config import FIGURES_DIR, LAND_MASK_DATASETS, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

ASSETS = FIGURES_DIR / "product_assets"
EXTENT_ID = "citywide"
BOUNDS = EXTENTS[EXTENT_ID]["bounds"]


def _citywide_land_geometry():
    """NYC borough coastlines (OSM-aligned) + Natural Earth land outside NYC, ocean punched."""
    from shapely.geometry import box
    from shapely.ops import unary_union

    clip = box(BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"])
    landcover = PROJECT_ROOT / "data" / "raw" / "landcover"
    borough_path = landcover / "nyc_boroughs2.geojson"
    if not borough_path.exists():
        import requests

        url = "https://raw.githubusercontent.com/dwillis/nyc-maps/master/boroughs.geojson"
        borough_path.write_bytes(
            requests.get(url, timeout=60, headers={"User-Agent": "nyc-flood-impact/1.0"}).content
        )
    archive = LAND_MASK_DATASETS["natural_earth_land"]
    ocean_zip = landcover / "ne_10m_ocean.zip"
    if not ocean_zip.exists():
        import requests

        ocean_zip.write_bytes(
            requests.get(
                "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_ocean.zip",
                timeout=120,
            ).content
        )
    if not archive.exists() or not zipfile.is_zipfile(archive):
        raise FileNotFoundError(f"Natural Earth land zip missing/invalid: {archive}")
    land_ne = gpd.read_file(f"zip://{archive}").to_crs("EPSG:4326").clip(clip)
    ne_u = unary_union(land_ne.geometry)
    if ocean_zip.exists() and zipfile.is_zipfile(ocean_zip):
        ocean = gpd.read_file(f"zip://{ocean_zip}").to_crs("EPSG:4326").clip(clip)
        if len(ocean):
            ne_u = ne_u.difference(unary_union(ocean.geometry))
    if borough_path.exists():
        boroughs = gpd.read_file(borough_path).to_crs("EPSG:4326")
        nyc = unary_union(boroughs.geometry)
        # Replace coarse NE coastline inside NYC with borough shorelines.
        # Slightly erode land (~40 m) so overlays don't bleed past OSM water edges.
        land = ne_u.difference(nyc.buffer(0.003)).union(nyc).buffer(-0.00035)
        if ocean_zip.exists() and zipfile.is_zipfile(ocean_zip):
            ocean = gpd.read_file(f"zip://{ocean_zip}").to_crs("EPSG:4326").clip(clip)
            if len(ocean):
                land = land.difference(unary_union(ocean.geometry))
        source = "NYC boroughs + Natural Earth 10m land/ocean (eroded ~40m)"
    else:
        land = ne_u
        source = "Natural Earth 10m land/ocean"
    geo_path = landcover / "land_mask_citywide.geojson"
    gpd.GeoDataFrame({"source": [source]}, geometry=[land], crs="EPSG:4326").to_file(
        geo_path, driver="GeoJSON"
    )
    return land, source


def build_citywide_land_mask(shape: tuple[int, int] = (720, 960)) -> tuple[np.ndarray, object]:
    land_geom, source = _citywide_land_geometry()
    transform = from_bounds(
        BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"], shape[1], shape[0]
    )
    mask = rio_features.geometry_mask(
        [land_geom],
        out_shape=shape,
        transform=transform,
        invert=True,  # True = land
    )
    out = PROCESSED_DIR / "land_mask_citywide.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": shape[0],
        "width": shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": 0,
        "compress": "deflate",
    }
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(mask.astype(np.uint8), 1)
        dst.update_tags(source=source, extent_id=EXTENT_ID)
    return mask.astype(bool), transform


def _warp_mask_to(mask_path: Path, height: int, width: int, transform) -> np.ndarray:
    dst = np.zeros((height, width), dtype=np.uint8)
    with rasterio.open(mask_path) as src:
        from rasterio.warp import reproject
        from rasterio.enums import Resampling

        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
        )
    return dst.astype(bool)


def mask_geotiff(path: Path, land: np.ndarray, transform) -> None:
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata if src.nodata is not None else -9999.0
        profile = src.profile.copy()
        land_r = _warp_mask_to(PROCESSED_DIR / "land_mask_citywide.tif", src.height, src.width, src.transform)
    data = np.where(land_r, data, nodata)
    profile.update(dtype="float32", nodata=nodata)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def mask_png(path: Path, land_mask_path: Path, bounds: list) -> None:
    """Zero alpha over water using land mask warped to PNG pixel grid."""
    im = np.array(Image.open(path).convert("RGBA"))
    h, w = im.shape[:2]
    # bounds are [[ymin,xmin],[ymax,xmax]] leaflet style
    transform = from_bounds(bounds[0][1], bounds[0][0], bounds[1][1], bounds[1][0], w, h)
    land = _warp_mask_to(land_mask_path, h, w, transform)
    # rasterio north-up: row0 = ymax; PIL row0 = top = ymax — same
    im[~land, 3] = 0
    Image.fromarray(im, mode="RGBA").save(path, optimize=True)


def main() -> None:
    print("Building citywide land mask…")
    mask, transform = build_citywide_land_mask()
    print(f"  land fraction={mask.mean():.3f}")
    mask_path = PROCESSED_DIR / "land_mask_citywide.tif"

    manifest = json.loads((ASSETS / "manifest.json").read_text())
    precip_bounds = manifest.get("precip", {}).get("bounds") or [
        [BOUNDS["ymin"], BOUNDS["xmin"]],
        [BOUNDS["ymax"], BOUNDS["xmax"]],
    ]
    mrms_bounds = (manifest.get("mrms_qpe") or {}).get("bounds") or precip_bounds
    pluvial_meta = json.loads((ASSETS / "pluvial_meta.json").read_text())
    pluvial_bounds = pluvial_meta.get("bounds") or precip_bounds

    # Mask GeoTIFFs
    for path in (PROCESSED_DIR / "earth2_precip").glob("*.tif"):
        mask_geotiff(path, mask, transform)
        print(f"  masked {path.name}")
    pluvial_tif = PROCESSED_DIR / "pluvial" / "pluvial_screening_citywide.tif"
    if pluvial_tif.exists():
        mask_geotiff(pluvial_tif, mask, transform)
    for path in (PROCESSED_DIR / "susceptibility").glob("*.tif"):
        mask_geotiff(path, mask, transform)
        print(f"  masked {path.name}")

    # Mask display PNGs for all storm paths (primary + alternate Earth2 scenarios)
    susc_bounds = (manifest.get("susceptibility") or {}).get("bounds") or precip_bounds
    pngs = []
    path_list = manifest.get("storm_paths") or [
        {"precip": manifest.get("precip"), "susceptibility": manifest.get("susceptibility")}
    ]
    for path in path_list:
        precip = path.get("precip") or {}
        susc = path.get("susceptibility") or {}
        pb = precip.get("bounds") or precip_bounds
        sb = susc.get("bounds") or susc_bounds
        for fr in precip.get("frames", []):
            pngs.append((ASSETS / fr["png"], pb))
        if precip.get("storm_total_png"):
            pngs.append((ASSETS / precip["storm_total_png"], pb))
        for fr in susc.get("frames", []):
            pngs.append((ASSETS / fr["png"], sb))
        for fr in (path.get("infra_highlights") or {}).get("frames", []) or []:
            pass  # vectors only
    # Also mask top-level precip/susc for backward compatibility
    for fr in manifest.get("precip", {}).get("frames", []):
        pngs.append((ASSETS / fr["png"], precip_bounds))
    if manifest.get("precip", {}).get("storm_total_png"):
        pngs.append((ASSETS / manifest["precip"]["storm_total_png"], precip_bounds))
    for fr in (manifest.get("susceptibility") or {}).get("frames", []):
        pngs.append((ASSETS / fr["png"], susc_bounds))
    pngs.append((ASSETS / "pluvial_screening.png", pluvial_bounds))
    if (ASSETS / "built_surface_proxy.png").exists():
        pngs.append((ASSETS / "built_surface_proxy.png", pluvial_bounds))
    # Deduplicate
    seen = set()
    uniq = []
    for path, bounds in pngs:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((path, bounds))
    pngs = uniq

    for path, bounds in pngs:
        if path.exists():
            mask_png(path, mask_path, bounds)
            print(f"  masked png {path.name}")

    meta = {
        "land_mask": str(mask_path),
        "source": "NYC boroughs + Natural Earth 10m land/ocean (eroded ~40m)",
        "extent_id": EXTENT_ID,
        "land_fraction": float(mask.mean()),
        "note": "Product rasters/PNGs alpha-masked over water so overlays follow OSM/borough coastlines.",
        "product_policy": "earth2_only",
    }
    (ASSETS / "land_mask_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
