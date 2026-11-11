#!/usr/bin/env python3
"""Build a valid South Queens SFINCS model and run via Deltares Docker.

No Earth2Studio Enterprise / HENS. Research only — NOT official NWS.

Exact docker commands used are written to outputs/sfincs_queens_docker_commands.txt
and docs/sfincs-docker-run.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

MODEL_DIR = OUTPUTS_DIR / "sfincs_queens_ida"
ASSETS = FIGURES_DIR / "product_assets"
IMAGE = "deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release"
# Prefer hi-res metro DEM; fall back to citywide / Queens 1/3".
DEM_CANDIDATES = [
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif",
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_1_3_arcsec.tif",
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif",
]
RAIN_CANDIDATES = [
    PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif",
    PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif",
    PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif",
]


def _first_existing(paths: list[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"None of {paths} exist")


def _docker(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run docker via `sg docker` so group membership applies in this session."""
    full = ["sg", "docker", "-c", " ".join(shlex_quote(c) for c in cmd)]
    return subprocess.run(full, check=False, capture_output=True, text=True)


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


def write_spatial_precip_netcdf(rain_tif: Path, out_nc: Path, hours: float = 12.0) -> dict:
    """Build HydroMT-ready NetCDF: spatially varying precip rate [mm/hr] over the event.

    Converts storm-total mm → rate = total/hours per cell (spatial field, never domain-mean).
    """
    import pandas as pd
    import rioxarray  # noqa: F401 — registers .rio accessor on DataArray

    with rasterio.open(rain_tif) as ds:
        arr = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            arr = np.where(arr == ds.nodata, np.nan, arr)
        transform = ds.transform
        height, width = arr.shape
        xs = np.array([transform.c + (i + 0.5) * transform.a for i in range(width)])
        ys = np.array([transform.f + (j + 0.5) * transform.e for j in range(height)])
        rate = np.clip(np.nan_to_num(arr, nan=0.0), 0, None) / hours  # mm/hr

    times = pd.date_range("2021-09-01T12:00:00", periods=2, freq=f"{int(hours)}h")
    # Two timesteps with the same spatial rate so HydroMT has a time axis covering the run.
    data = np.stack([rate, rate], axis=0).astype(np.float32)
    da = xr.DataArray(
        data,
        coords={"time": times, "y": ys, "x": xs},
        dims=("time", "y", "x"),
        name="precip",
    )
    da.attrs["units"] = "mm/hr"
    da = da.rio.write_crs("EPSG:4326")
    da = da.rio.write_transform(transform)
    out_nc.parent.mkdir(parents=True, exist_ok=True)
    ds_out = da.to_dataset()
    ds_out.to_netcdf(out_nc)
    finite = rate[np.isfinite(rate) & (rate > 0)]
    return {
        "path": str(out_nc),
        "source_tif": str(rain_tif),
        "hours": hours,
        "mean_rate_mm_hr": float(finite.mean()) if finite.size else None,
        "max_rate_mm_hr": float(finite.max()) if finite.size else None,
        "cv": float(finite.std() / finite.mean()) if finite.size else None,
        "spatial": True,
        "uniform_mean_forbidden": True,
    }


def build_model() -> dict:
    # hydromt_sfincs 1.2.x uses deprecated pandas freq "10T"; patch for pandas 2.2+
    import pandas as pd

    _orig_date_range = pd.date_range

    def _date_range(*args, **kwargs):
        freq = kwargs.get("freq")
        if isinstance(freq, str) and freq.endswith("T") and not freq.endswith("min"):
            kwargs["freq"] = freq[:-1] + "min"
        return _orig_date_range(*args, **kwargs)

    pd.date_range = _date_range  # type: ignore[assignment]

    from hydromt_sfincs import SfincsModel

    dem = _first_existing(DEM_CANDIDATES)
    rain = _first_existing(RAIN_CANDIDATES)

    if MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    MODEL_DIR.mkdir(parents=True)

    precip_nc = MODEL_DIR / "forcing" / "mrms_spatial_precip_mmhr.nc"
    precip_meta = write_spatial_precip_netcdf(rain, precip_nc, hours=12.0)

    b = EXTENTS["south_queens"]["bounds"]
    # HydroMT region bbox: [xmin, ymin, xmax, ymax] in WGS84
    region = {"bbox": [b["xmin"], b["ymin"], b["xmax"], b["ymax"]]}

    sf = SfincsModel(root=str(MODEL_DIR), mode="w+")
    # ~50 m grid in UTM
    sf.setup_grid_from_region(region=region, res=50, crs="utm")
    sf.setup_config(
        tref="20210901 120000",
        tstart="20210901 120000",
        tstop="20210902 000000",  # 12 h
        dtout=3600,
        dthisout=600,
        dtmaxout=43200,
        alpha=0.5,
        theta=1.0,
        manning=0.04,
        huthresh=0.01,
    )
    # Local DEM as elevation source
    sf.setup_dep(datasets_dep=[{"elevtn": str(dem), "reproj_method": "bilinear"}])
    sf.setup_mask_active(zmin=-5.0)  # keep land/nearshore cells
    # Spatial MRMS precip — never setup_precip_forcing(magnitude=domain_mean)
    sf.setup_precip_forcing_from_grid(
        precip=str(precip_nc),
        cumulative_input=False,
        aggregate=False,
    )
    sf.write()

    meta = {
        "model_dir": str(MODEL_DIR),
        "extent": "south_queens",
        "res_m": 50,
        "precip_forcing": "spatial_mrms_grid",
        "precip_netcdf": precip_meta,
        "precip_source": str(rain),
        "dem": str(dem),
        "tstart": "20210901 120000",
        "tstop": "20210902 000000",
        "enterprise": False,
        "hens": False,
        "official_nws": False,
        "note": "Dropped uniform setup_precip_forcing(magnitude=mean); using spatial MRMS rate field.",
    }
    (MODEL_DIR / "build_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def run_docker(meta: dict) -> dict:
    model_abs = str(MODEL_DIR.resolve())
    cmds = [
        f"sg docker -c 'docker pull {IMAGE}'",
        (
            f"sg docker -c 'docker run --rm "
            f"-v {model_abs}:/data {IMAGE}'"
        ),
    ]
    cmd_path = OUTPUTS_DIR / "sfincs_queens_docker_commands.txt"
    cmd_path.write_text("\n".join(cmds) + "\n")

    pull = _docker(["docker", "pull", IMAGE])
    run = _docker(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{model_abs}:/data",
            IMAGE,
        ]
    )
    log = {
        "image": IMAGE,
        "commands": cmds,
        "pull_returncode": pull.returncode,
        "run_returncode": run.returncode,
        "pull_stdout_tail": (pull.stdout or "")[-2000:],
        "pull_stderr_tail": (pull.stderr or "")[-2000:],
        "run_stdout_tail": (run.stdout or "")[-4000:],
        "run_stderr_tail": (run.stderr or "")[-4000:],
        "model_dir": model_abs,
        "files_after": sorted(p.name for p in MODEL_DIR.iterdir()),
    }
    (OUTPUTS_DIR / "sfincs_queens_docker_log.json").write_text(json.dumps(log, indent=2))
    (MODEL_DIR / "docker_run_log.json").write_text(json.dumps(log, indent=2))
    if run.returncode != 0:
        raise RuntimeError(f"SFINCS docker run failed: {run.stderr or run.stdout}")
    return log


def export_depth_geotiff() -> dict:
    """Read SFINCS netCDF max depth / zs and write GeoTIFF + PNG for the product map."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import colormaps
    from PIL import Image

    # Common SFINCS output names
    candidates = [
        MODEL_DIR / "sfincs_map.nc",
        MODEL_DIR / "sfincs_his.nc",
        MODEL_DIR / "sfincs_map.nc",
    ]
    # Also search
    ncs = list(MODEL_DIR.glob("*.nc"))
    if not ncs:
        raise FileNotFoundError(f"No NetCDF outputs in {MODEL_DIR}: {list(MODEL_DIR.iterdir())}")

    map_nc = next((p for p in ncs if "map" in p.name.lower()), ncs[0])
    ds = xr.open_dataset(map_nc)
    # Prefer hmax / zsmax / h
    var = None
    for name in ("hmax", "zsmax", "h", "waterdepth", "depth"):
        if name in ds:
            var = name
            break
    if var is None:
        # last resort: first data var with 2+ dims
        for name, da in ds.data_vars.items():
            if da.ndim >= 2:
                var = name
                break
    if var is None:
        raise RuntimeError(f"No depth-like variable in {map_nc}: {list(ds.data_vars)}")

    da = ds[var]
    if "timemax" in da.dims:
        da = da.isel(timemax=-1)
    elif "time" in da.dims:
        da = da.max("time")
    depth = np.asarray(da.values, dtype=np.float32)
    depth = np.where(np.isfinite(depth) & (depth > 0), depth, np.nan)

    # Coordinates — SFINCS often uses x/y in projected CRS
    if "x" in da.coords and "y" in da.coords:
        xs = np.asarray(da["x"].values)
        ys = np.asarray(da["y"].values)
    elif "corner_x" in ds and "corner_y" in ds:
        # cell centers approx
        xs = np.asarray(ds["corner_x"].values)
        ys = np.asarray(ds["corner_y"].values)
        if xs.ndim == 2:
            # take midpoints of edges
            xs = 0.5 * (xs[:, :-1] + xs[:, 1:]) if xs.shape[1] > 1 else xs
            ys = 0.5 * (ys[:-1, :] + ys[1:, :]) if ys.shape[0] > 1 else ys
            # flatten to 1d axes if possible
            if depth.ndim == 2 and xs.ndim == 2:
                xs = xs[0, :] if xs.shape[0] == depth.shape[0] else xs[:, 0]
                ys = ys[:, 0] if ys.shape[1] == depth.shape[1] else ys[0, :]
    else:
        raise RuntimeError(f"Cannot find x/y coords in {map_nc}")

    # Ensure 2D depth matches
    if depth.ndim > 2:
        depth = np.squeeze(depth)
    # Build affine from regular grid if possible
    from affine import Affine
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.warp import transform as warp_xy

    # Read EPSG from inp
    epsg = 32618
    inp = (MODEL_DIR / "sfincs.inp").read_text()
    for line in inp.splitlines():
        if line.strip().startswith("epsg"):
            epsg = int(line.split("=")[1].strip())

    # If x/y are 1D
    if xs.ndim == 1 and ys.ndim == 1:
        # SFINCS y may be ascending or descending
        dx = float(np.median(np.diff(xs))) if len(xs) > 1 else 50.0
        dy = float(np.median(np.diff(ys))) if len(ys) > 1 else 50.0
        west = float(xs.min() - abs(dx) / 2)
        north = float(ys.max() + abs(dy) / 2)
        transform = from_origin(west, north, abs(dx), abs(dy))
        if dy > 0 and ys[0] < ys[-1]:
            depth = np.flipud(depth)
    else:
        # fallback: write with geotransform from bounds
        transform = from_origin(float(np.nanmin(xs)), float(np.nanmax(ys)), 50.0, 50.0)

    out_dir = PROCESSED_DIR / "inundation"
    out_dir.mkdir(parents=True, exist_ok=True)
    tif_utm = out_dir / "depth_sfincs_queens_ida_utm.tif"
    with rasterio.open(
        tif_utm,
        "w",
        driver="GTiff",
        height=depth.shape[0],
        width=depth.shape[1],
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(epsg),
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(depth.astype(np.float32), 1)

    # Reproject to WGS84 citywide display grid matching pysheds Queens clip
    b = EXTENTS["south_queens"]["bounds"]
    # Match existing queens depth grid if present
    ref = out_dir / "depth_south_queens_mrms_qpe_ida_storm_total_m.tif"
    if ref.exists():
        with rasterio.open(ref) as src:
            dst_shape = (src.height, src.width)
            dst_transform = src.transform
            dst_crs = src.crs
    else:
        # ~same as DEM clip resolution
        from rasterio.transform import from_bounds

        dst_shape = (217, 481)
        dst_transform = from_bounds(b["xmin"], b["ymin"], b["xmax"], b["ymax"], dst_shape[1], dst_shape[0])
        dst_crs = "EPSG:4326"

    from rasterio.warp import Resampling, reproject

    dest = np.full(dst_shape, np.nan, dtype=np.float32)
    with rasterio.open(tif_utm) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )

    tif = out_dir / "depth_sfincs_queens_ida_m.tif"
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        height=dest.shape[0],
        width=dest.shape[1],
        count=1,
        dtype="float32",
        crs=dst_crs,
        transform=dst_transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(dest, 1)

    # PNG
    vmax = float(np.nanpercentile(dest[np.isfinite(dest)], 98)) if np.isfinite(dest).any() else 0.5
    vmax = max(vmax, 0.05)
    cmap = colormaps["Blues"]
    norm = np.clip(np.nan_to_num(dest, nan=0.0) / vmax, 0, 1)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(dest) & (dest > 0.005), np.clip(80 + norm * 175, 0, 255).astype(np.uint8), 0)
    png = ASSETS / "depth_sfincs_queens_ida_m.png"
    Image.fromarray(rgba, "RGBA").save(png)

    meta = {
        "engine": "sfincs_docker_v2.1.1_Dollerup",
        "image": IMAGE,
        "tif": str(tif),
        "png": png.name,
        "max_m": float(np.nanmax(dest)) if np.isfinite(dest).any() else None,
        "wet_fraction": float(np.mean(np.isfinite(dest) & (dest > 0.005))),
        "extent": "south_queens",
        "forcing": "spatial_mrms_precip_2d",
        "role": "alternate_hydro_track",
        "primary": False,
        "official_nws": False,
        "decision_grade": False,
        "enterprise": False,
        "hens": False,
        "source_nc": str(map_nc),
        "variable": var,
        "honesty": (
            "SFINCS depth from Deltares Docker on HydroMT Queens model with "
            "spatially varying MRMS Ida precip (not domain-mean). Alternate hydro track — "
            "NOT peer-authoritative with primary pysheds metro depth until calibrated/comparable."
        ),
    }
    (out_dir / "depth_sfincs_queens_ida_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "depth_sfincs_queens_ida_meta.json").write_text(json.dumps(meta, indent=2))
    ds.close()
    return meta


def wire_manifest(sfincs_meta: dict) -> None:
    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["inundation_sfincs"] = {
            "png": sfincs_meta["png"],
            "meta": "depth_sfincs_queens_ida_meta.json",
            "engine": sfincs_meta["engine"],
            "extent": "south_queens",
            "compare_with": "inundation_borough_spike",
        }
        mp.write_text(json.dumps(m, indent=2))


def write_docs(meta: dict, log: dict, depth: dict) -> None:
    docs = PROJECT_ROOT / "docs" / "sfincs-docker-run.md"
    docs.write_text(
        f"""# SFINCS Docker run — South Queens / Ida

**No Enterprise / HENS. Research only — NOT official NWS.**

## Exact commands used

```bash
# Session needs docker group (use sg if freshly added to group):
sg docker -c 'docker pull {IMAGE}'

sg docker -c 'docker run --rm -v {MODEL_DIR.resolve()}:/data {IMAGE}'
```

Logged copy: `outputs/sfincs_queens_docker_commands.txt`

## Model

- Built with HydroMT-SFINCS `{__import__('hydromt_sfincs').__version__}` into `outputs/sfincs_queens_ida/`
- DEM: `{meta.get('dem')}` clipped via HydroMT region (South Queens bbox)
- Forcing: **spatial** MRMS precip grid (`setup_precip_forcing_from_grid`, aggregate=False) — not domain-mean
- Precip NetCDF: `{meta.get('precip_netcdf', {}).get('path')}`
- Rate stats (mm/hr): mean≈{meta.get('precip_netcdf', {}).get('mean_rate_mm_hr')}, max≈{meta.get('precip_netcdf', {}).get('max_rate_mm_hr')}, CV≈{meta.get('precip_netcdf', {}).get('cv')}
- Window: 2021-09-01 12Z → 2021-09-02 00Z

## Outputs

- Depth GeoTIFF: `data/processed/inundation/depth_sfincs_queens_ida_m.tif`
- PNG overlay: `figures/product_assets/depth_sfincs_queens_ida_m.png`
- Max depth ≈ **{depth.get('max_m')}** m (research)

## vs pysheds (primary)

- **Primary depth** = metro pysheds HAND/bathtub × spatial MRMS
- **SFINCS Queens** = alternate hydro track only (not peer toggle for magnitudes)

Compare visually; do not treat either as calibrated DEP/NWS inundation.

## Docker log summary

- pull rc: {log.get('pull_returncode')}
- run rc: {log.get('run_returncode')}
- image digest pull: see `outputs/sfincs_queens_docker_log.json`
"""
    )


def main() -> None:
    print("Building HydroMT SFINCS model…")
    meta = build_model()
    print(json.dumps(meta, indent=2))
    print("Running SFINCS via Docker…")
    log = run_docker(meta)
    print("Exporting depth…")
    depth = export_depth_geotiff()
    wire_manifest(depth)
    write_docs(meta, log, depth)
    # copy commands + docs to assets
    shutil.copy(OUTPUTS_DIR / "sfincs_queens_docker_commands.txt", ASSETS / "sfincs_queens_docker_commands.txt")
    print(json.dumps({"depth": depth, "docker_rc": log["run_returncode"]}, indent=2))


if __name__ == "__main__":
    main()
