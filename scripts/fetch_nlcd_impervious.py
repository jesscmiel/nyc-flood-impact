#!/usr/bin/env python3
"""Fetch a clipped NLCD 2021 percent-impervious GeoTIFF for the study extent.

Uses the public MRLC GeoServer WCS (not the multi-GB CONUS zip). Output is
percent impervious 0–100 (uint8), suitable for pluvial screening.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from nyc_flash_flood_case_study.extents import EXTENTS

MRLC_WCS = "https://www.mrlc.gov/geoserver/mrlc_download/wcs"
COVERAGE = "mrlc_download:NLCD_2021_Impervious_L48"


def fetch_nlcd_impervious(extent_id: str = "south_queens", out: Path | None = None) -> Path:
    extent = EXTENTS[extent_id]
    b = extent["bounds"]
    # ~30 m at mid-lat
    lat_m = 111_320.0
    lon_m = 111_320.0 * float(np.cos(np.deg2rad(0.5 * (b["ymin"] + b["ymax"]))))
    width = max(64, int(round((b["xmax"] - b["xmin"]) * lon_m / 30.0)))
    height = max(64, int(round((b["ymax"] - b["ymin"]) * lat_m / 30.0)))
    out = out or (
        Path(__file__).resolve().parents[1]
        / "data"
        / "raw"
        / "landcover"
        / f"nlcd_2021_impervious_{extent_id}.tif"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    params = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": COVERAGE,
        "CRS": "EPSG:4326",
        "BBOX": f"{b['xmin']},{b['ymin']},{b['xmax']},{b['ymax']}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "GeoTIFF",
    }
    url = f"{MRLC_WCS}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "nyc-flood-impact/0.1"})
    with urlopen(req, timeout=180) as resp:  # noqa: S310
        payload = resp.read()
    if payload[:200].lstrip().startswith(b"<"):
        raise RuntimeError(f"MRLC WCS returned XML error: {payload[:500]!r}")

    tmp = out.with_suffix(".download.tif")
    tmp.write_bytes(payload)

    # Normalize to a clean single-band percent GeoTIFF with explicit tags.
    with rasterio.open(tmp) as src:
        data = src.read(1)
        transform = from_bounds(b["xmin"], b["ymin"], b["xmax"], b["ymax"], width, height)
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "uint8",
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": 127,  # NLCD often uses 127 for NA in impervious products
            "compress": "deflate",
        }
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(data.astype(np.uint8), 1)
            dst.update_tags(
                source="MRLC NLCD 2021 Impervious L48 via WCS",
                coverage=COVERAGE,
                units="percent_impervious_0_100",
                extent_id=extent_id,
                interpretation="NLCD percent impervious surface; not flood depth.",
            )
    tmp.unlink(missing_ok=True)

    # Also refresh the conventional path used by config.LANDCOVER_DATASETS
    canonical = out.parent / "impervious_surface.tif"
    with rasterio.open(out) as src:
        profile = src.profile.copy()
        data = src.read(1).astype(np.float32)
        # Store as 0–1 float for older hydrology paths; keep nodata
        nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, -9999.0, data / 100.0)
        else:
            data = data / 100.0
        profile.update(dtype="float32", nodata=-9999.0)
        with rasterio.open(canonical, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                source="Derived from NLCD 2021 Impervious (fraction 0-1)",
                parent=str(out),
            )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extent", default="south_queens")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    path = fetch_nlcd_impervious(args.extent, args.out)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
