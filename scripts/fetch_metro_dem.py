#!/usr/bin/env python3
"""Fetch hi-res USGS 3DEP DEM for NYC metro bounds (target ≤10 m).

Uses tiled ImageServer exportImage in EPSG:3857 (single huge WGS84 exports fail),
mosaics tiles, reprojects to EPSG:4326 metro grid, writes dem_usgs_metro.tif.

Research terrain only — never invents elevation.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject

from nyc_flash_flood_case_study.config import RAW_DIR
from nyc_flash_flood_case_study.extents import EXTENTS

BOUNDS = EXTENTS["metro"]["bounds"]
OUT = RAW_DIR / "terrain" / "dem_usgs_metro.tif"
META_OUT = RAW_DIR / "terrain" / "dem_metro_fetch.json"
IMAGE_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
)
TARGET_RES_M = 10.0
# ImageServer reliably serves ~2000–3000 px; stay under that per tile.
MAX_TILE_PX = 1600  # safer vs ImageServer 504s at ~2000²
UA = {"User-Agent": "nyc-flood-impact/1.0"}


def _lonlat_to_merc(lon: float, lat: float) -> tuple[float, float]:
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * 20037508.34 / 180.0
    return x, y


def _merc_bounds(b: dict[str, float]) -> tuple[float, float, float, float]:
    x0, y0 = _lonlat_to_merc(b["xmin"], b["ymin"])
    x1, y1 = _lonlat_to_merc(b["xmax"], b["ymax"])
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _tile_windows(
    xmin: float, ymin: float, xmax: float, ymax: float, res_m: float, max_px: int
) -> list[tuple[float, float, float, float, int, int]]:
    width_m = xmax - xmin
    height_m = ymax - ymin
    max_span = max_px * res_m
    nx = max(1, math.ceil(width_m / max_span))
    ny = max(1, math.ceil(height_m / max_span))
    tiles = []
    for iy in range(ny):
        for ix in range(nx):
            x0 = xmin + ix * (width_m / nx)
            x1 = xmin + (ix + 1) * (width_m / nx)
            y0 = ymin + iy * (height_m / ny)
            y1 = ymin + (iy + 1) * (height_m / ny)
            w = max(1, int(round((x1 - x0) / res_m)))
            h = max(1, int(round((y1 - y0) / res_m)))
            # Clamp to ImageServer-safe sizes
            w = min(w, max_px)
            h = min(h, max_px)
            tiles.append((x0, y0, x1, y1, w, h))
    return tiles


def _fetch_tile(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    width: int,
    height: int,
    out_path: Path,
    *,
    retries: int = 4,
) -> dict:
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": 3857,
        "imageSR": 3857,
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    info: dict = {
        "size": [width, height],
        "bbox_3857": [xmin, ymin, xmax, ymax],
        "path": str(out_path),
        "attempts": 0,
    }
    last_err = None
    for attempt in range(1, retries + 1):
        info["attempts"] = attempt
        try:
            r = requests.get(IMAGE_URL, params=params, timeout=300, headers=UA)
            info["http_status"] = r.status_code
            info["nbytes"] = len(r.content)
            if r.status_code != 200 or len(r.content) < 1000:
                last_err = f"http_{r.status_code}"
                info["body_head"] = (r.text or "")[:200]
                # Shrink tile on 5xx / timeout-like failures
                if attempt < retries and width > 900 and height > 900:
                    width = max(900, width // 2)
                    height = max(900, height // 2)
                    params["size"] = f"{width},{height}"
                    info["size"] = [width, height]
                import time

                time.sleep(2 * attempt)
                continue
            with MemoryFile(r.content) as mem:
                with mem.open() as src:
                    data = src.read(1).astype(np.float32)
                    profile = src.profile.copy()
                    profile.update(
                        driver="GTiff",
                        compress="deflate",
                        nodata=-9999.0,
                        dtype="float32",
                        count=1,
                    )
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with rasterio.open(out_path, "w", **profile) as dst:
                        dst.write(np.where(np.isfinite(data), data, -9999.0), 1)
                    info.update(
                        {
                            "status": "ok",
                            "shape": list(data.shape),
                            "res": list(src.res),
                            "crs": str(src.crs),
                        }
                    )
            return info
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            import time

            time.sleep(2 * attempt)
    info["status"] = "failed_http"
    info["error"] = last_err
    return info


def fetch(target_res_m: float = TARGET_RES_M) -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    mx0, my0, mx1, my1 = _merc_bounds(BOUNDS)
    tiles = _tile_windows(mx0, my0, mx1, my1, target_res_m, MAX_TILE_PX)
    meta: dict = {
        "extent": "metro",
        "bounds_wgs84": BOUNDS,
        "bounds_3857": [mx0, my0, mx1, my1],
        "target_res_m": target_res_m,
        "n_tiles": len(tiles),
        "path": str(OUT),
        "status": "pending",
        "tiles": [],
    }

    with tempfile.TemporaryDirectory(prefix="dem_metro_") as td:
        td_path = Path(td)
        tile_paths: list[Path] = []
        for i, (x0, y0, x1, y1, w, h) in enumerate(tiles):
            tp = td_path / f"tile_{i:03d}.tif"
            print(f"Fetching tile {i+1}/{len(tiles)} {w}x{h}…", flush=True)
            info = _fetch_tile(x0, y0, x1, y1, w, h, tp)
            meta["tiles"].append(info)
            if info.get("status") != "ok":
                # Split failed tile into 4 quadrants and retry once more
                print(f"  tile {i} failed — splitting into quadrants…", flush=True)
                mx = 0.5 * (x0 + x1)
                my = 0.5 * (y0 + y1)
                quads = [
                    (x0, y0, mx, my),
                    (mx, y0, x1, my),
                    (x0, my, mx, y1),
                    (mx, my, x1, y1),
                ]
                ok_quads: list[Path] = []
                for qi, (qx0, qy0, qx1, qy1) in enumerate(quads):
                    qw = max(1, int(round((qx1 - qx0) / target_res_m)))
                    qh = max(1, int(round((qy1 - qy0) / target_res_m)))
                    qw = min(qw, MAX_TILE_PX)
                    qh = min(qh, MAX_TILE_PX)
                    qp = td_path / f"tile_{i:03d}_q{qi}.tif"
                    qinfo = _fetch_tile(qx0, qy0, qx1, qy1, qw, qh, qp)
                    meta["tiles"].append({**qinfo, "parent_tile": i, "quad": qi})
                    if qinfo.get("status") != "ok":
                        meta["status"] = "tile_failed"
                        META_OUT.write_text(json.dumps(meta, indent=2))
                        print(json.dumps({k: meta[k] for k in meta if k != "tiles"}, indent=2))
                        return meta
                    ok_quads.append(qp)
                tile_paths.extend(ok_quads)
                continue
            tile_paths.append(tp)

        # Mosaic in Web Mercator
        datasets = [rasterio.open(p) for p in tile_paths]
        try:
            mosaic, transform = merge(datasets, nodata=-9999.0)
            mosaic = mosaic[0].astype(np.float32)
            mosaic = np.where(mosaic == -9999.0, np.nan, mosaic)
            src_crs = datasets[0].crs
        finally:
            for ds in datasets:
                ds.close()

        # Target WGS84 grid at ~target_res_m
        dest_crs = "EPSG:4326"
        left, bottom, right, top = BOUNDS["xmin"], BOUNDS["ymin"], BOUNDS["xmax"], BOUNDS["ymax"]
        # Approximate degrees for target_res_m at mid-lat
        mid_lat = 0.5 * (bottom + top)
        m_lon = 111320.0 * math.cos(math.radians(mid_lat))
        m_lat = 110540.0
        width = max(1, int(round((right - left) * m_lon / target_res_m)))
        height = max(1, int(round((top - bottom) * m_lat / target_res_m)))
        dst_transform = from_bounds(left, bottom, right, top, width, height)
        dest = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=mosaic,
            destination=dest,
            src_transform=transform,
            src_crs=src_crs,
            src_nodata=np.nan,
            dst_transform=dst_transform,
            dst_crs=dest_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )

        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "float32",
            "crs": dest_crs,
            "transform": dst_transform,
            "compress": "deflate",
            "nodata": -9999.0,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }
        with rasterio.open(OUT, "w", **profile) as dst:
            dst.write(np.where(np.isfinite(dest), dest, -9999.0), 1)
            dst.update_tags(
                source="USGS 3DEP Elevation ImageServer (tiled EPSG:3857 mosaic)",
                extent="metro",
                target_res_m=str(target_res_m),
            )

        finite = np.isfinite(dest) & (dest > -500) & (dest < 3000)
        cell_m = [
            abs(dst_transform.a) * m_lon,
            abs(dst_transform.e) * m_lat,
        ]
        meta.update(
            {
                "status": "ok" if finite.any() else "empty",
                "shape": [height, width],
                "approx_cell_m": cell_m,
                "finite_fraction": float(finite.mean()),
                "min": float(dest[finite].min()) if finite.any() else None,
                "max": float(dest[finite].max()) if finite.any() else None,
                "nbytes": OUT.stat().st_size if OUT.exists() else None,
            }
        )

    META_OUT.write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: meta[k] for k in meta if k != "tiles"}, indent=2))
    print(f"tiles_ok={sum(1 for t in meta['tiles'] if t.get('status')=='ok')}/{len(meta['tiles'])}")
    return meta


if __name__ == "__main__":
    fetch()
