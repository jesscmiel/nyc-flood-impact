"""Metro nested SFINCS helpers — Advanced research hydro track only.

Primary product depth remains HAND/bathtub. This module never claims DEP sewer
or SWMM; drainage is the open capacity proxy (literature mm/hr sink).

No Earth2Studio Enterprise / HENS. Research only — NOT official NWS.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import xarray as xr

ENGINE_ID = "sfincs_metro_nested_v1"
ENGINE_LABEL = "SFINCS metro nested (coarse + Queens fine) — Advanced research only"
IMAGE = "deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release"

# Coarse metro ~100 m; Queens nest stays ~50 m (existing spike resolution).
METRO_RES_M = 100
NEST_RES_M = 50


def shlex_quote(s: str) -> str:
    return shlex.quote(s)


def docker_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run docker via `sg docker` so group membership applies in this session."""
    full = ["sg", "docker", "-c", " ".join(shlex_quote(c) for c in cmd)]
    return subprocess.run(full, check=False, capture_output=True, text=True)


def patch_pandas_freq() -> None:
    """HydroMT-SFINCS 1.2.x still uses deprecated pandas freq '10T'."""
    import pandas as pd

    _orig = pd.date_range

    def _date_range(*args: Any, **kwargs: Any):
        freq = kwargs.get("freq")
        if isinstance(freq, str) and freq.endswith("T") and not freq.endswith("min"):
            kwargs["freq"] = freq[:-1] + "min"
        return _orig(*args, **kwargs)

    pd.date_range = _date_range  # type: ignore[assignment]


def write_spatial_precip_netcdf(
    rain_tif: Path,
    out_nc: Path,
    hours: float = 12.0,
    *,
    apply_drainage_proxy: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    """Build HydroMT-ready NetCDF: spatially varying precip rate [mm/hr].

    Converts storm-total mm → rate = total/hours per cell (never domain-mean).
    Optionally applies open drainage capacity proxy — NOT DEP sewer / NOT SWMM.
    """
    import pandas as pd
    import rioxarray  # noqa: F401 — registers .rio accessor

    from flood_risk.inundation.drainage_capacity import (
        apply_capacity_to_rate_mm_hr,
        capacity_mm_hr,
        default_drain_candidate_paths,
        drain_density_norm,
        load_drain_points,
        load_impervious_fraction,
    )

    root = root or Path(__file__).resolve().parents[2]
    figures = root / "figures" / "product_assets"
    raw = root / "data" / "raw"

    with rasterio.open(rain_tif) as ds:
        arr = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            arr = np.where(arr == ds.nodata, np.nan, arr)
        transform = ds.transform
        crs = ds.crs
        height, width = arr.shape
        xs = np.array([transform.c + (i + 0.5) * transform.a for i in range(width)])
        ys = np.array([transform.f + (j + 0.5) * transform.e for j in range(height)])
        rate_raw = np.clip(np.nan_to_num(arr, nan=0.0), 0, None) / hours

    drainage_meta: dict[str, Any] = {"applied": False, "not_dep_sewer": True, "not_swmm": True}
    rate = rate_raw
    if apply_drainage_proxy:
        nlcd = raw / "landcover" / "nlcd_2021_impervious_citywide.tif"
        if nlcd.exists():
            impervious = load_impervious_fraction((height, width), transform, crs, nlcd)
            pts, dpath, dstatus = load_drain_points(
                default_drain_candidate_paths(raw / "infrastructure", figures, raw)
            )
            cap = capacity_mm_hr(impervious, drain_density_norm((height, width), transform, pts))
            rate, eff = apply_capacity_to_rate_mm_hr(rate_raw, cap)
            drainage_meta = {
                "applied": True,
                "engine": "drainage_capacity_proxy_v1",
                "drain_points_n": len(pts),
                "drain_status": dstatus,
                "drain_path": str(dpath) if dpath else None,
                "mean_efficiency": float(np.nanmean(eff)) if np.isfinite(eff).any() else None,
                "mean_rate_raw_mm_hr": float(np.nanmean(rate_raw[rate_raw > 0]))
                if (rate_raw > 0).any()
                else None,
                "not_dep_sewer": True,
                "not_swmm": True,
            }

    times = pd.date_range("2021-09-01T12:00:00", periods=2, freq=f"{int(hours)}h")
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
    da.to_dataset().to_netcdf(out_nc)
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
        "drainage_capacity_proxy": drainage_meta,
        "shared_sink": True,
    }


def build_sfincs_model(
    *,
    model_dir: Path,
    dem: Path,
    rain_tif: Path,
    extent_bounds: dict[str, float],
    res_m: float,
    label: str,
    apply_drainage_proxy: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    """Build a HydroMT-SFINCS model with spatial MRMS (+ optional drainage sink)."""
    patch_pandas_freq()
    from hydromt_sfincs import SfincsModel

    if model_dir.exists():
        shutil.rmtree(model_dir)
    model_dir.mkdir(parents=True)

    precip_nc = model_dir / "forcing" / "mrms_spatial_precip_mmhr.nc"
    precip_meta = write_spatial_precip_netcdf(
        rain_tif,
        precip_nc,
        hours=12.0,
        apply_drainage_proxy=apply_drainage_proxy,
        root=root,
    )

    region = {
        "bbox": [
            extent_bounds["xmin"],
            extent_bounds["ymin"],
            extent_bounds["xmax"],
            extent_bounds["ymax"],
        ]
    }
    sf = SfincsModel(root=str(model_dir), mode="w+")
    sf.setup_grid_from_region(region=region, res=res_m, crs="utm")
    sf.setup_config(
        tref="20210901 120000",
        tstart="20210901 120000",
        tstop="20210902 000000",
        dtout=3600,
        dthisout=600,
        dtmaxout=43200,
        alpha=0.5,
        theta=1.0,
        manning=0.04,
        huthresh=0.01,
    )
    sf.setup_dep(datasets_dep=[{"elevtn": str(dem), "reproj_method": "bilinear"}])
    sf.setup_mask_active(zmin=-5.0)
    sf.setup_precip_forcing_from_grid(
        precip=str(precip_nc),
        cumulative_input=False,
        aggregate=False,
    )
    sf.write()

    meta = {
        "engine_id": ENGINE_ID,
        "label": label,
        "model_dir": str(model_dir),
        "res_m": res_m,
        "precip_forcing": "spatial_mrms_grid",
        "precip_netcdf": precip_meta,
        "precip_source": str(rain_tif),
        "dem": str(dem),
        "extent_bounds": extent_bounds,
        "tstart": "20210901 120000",
        "tstop": "20210902 000000",
        "primary": False,
        "role": "advanced_research_hydro",
        "not_swmm": True,
        "enterprise": False,
        "hens": False,
        "official_nws": False,
        "decision_grade": False,
        "note": (
            "Spatial MRMS + drainage_capacity_proxy_v1 sink. "
            "Uniform domain-mean forcing forbidden. Not SWMM / not DEP."
        ),
    }
    (model_dir / "build_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def run_sfincs_docker(model_dir: Path, *, log_path: Path, commands_path: Path) -> dict[str, Any]:
    model_abs = str(model_dir.resolve())
    cmds = [
        f"sg docker -c 'docker pull {IMAGE}'",
        f"sg docker -c 'docker run --rm -v {model_abs}:/data {IMAGE}'",
    ]
    commands_path.write_text("\n".join(cmds) + "\n")
    pull = docker_run(["docker", "pull", IMAGE])
    run = docker_run(["docker", "run", "--rm", "-v", f"{model_abs}:/data", IMAGE])
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
        "files_after": sorted(p.name for p in model_dir.iterdir()),
    }
    log_path.write_text(json.dumps(log, indent=2))
    (model_dir / "docker_run_log.json").write_text(json.dumps(log, indent=2))
    if run.returncode != 0:
        raise RuntimeError(f"SFINCS docker run failed for {model_dir}: {run.stderr or run.stdout}")
    return log


def export_depth_from_map_nc(
    model_dir: Path,
    *,
    out_tif: Path,
    out_png: Path,
    out_meta: Path,
    extent_bounds: dict[str, float],
    ref_tif: Path | None = None,
    label: str = "sfincs",
) -> dict[str, Any]:
    """Read SFINCS map NetCDF max depth and write WGS84 GeoTIFF + PNG."""
    import matplotlib

    matplotlib.use("Agg")
    from affine import Affine  # noqa: F401
    from matplotlib import colormaps
    from PIL import Image
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds, from_origin
    from rasterio.warp import Resampling, reproject

    ncs = list(model_dir.glob("*.nc"))
    if not ncs:
        raise FileNotFoundError(f"No NetCDF outputs in {model_dir}")
    map_nc = next((p for p in ncs if "map" in p.name.lower()), ncs[0])
    ds = xr.open_dataset(map_nc)
    var = None
    for name in ("hmax", "zsmax", "h", "waterdepth", "depth"):
        if name in ds:
            var = name
            break
    if var is None:
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

    if "x" in da.coords and "y" in da.coords:
        xs = np.asarray(da["x"].values)
        ys = np.asarray(da["y"].values)
    elif "x" in ds.coords and "y" in ds.coords:
        xs = np.asarray(ds["x"].values)
        ys = np.asarray(ds["y"].values)
    else:
        raise RuntimeError(f"Cannot find x/y coords in {map_nc}")

    if depth.ndim > 2:
        depth = np.squeeze(depth)

    # SFINCS map often stores regular grids as 2D mesh coordinates (n, m).
    if xs.ndim == 2 and ys.ndim == 2:
        xs_1d = xs[0, :] if xs.shape == depth.shape else xs[:, 0]
        ys_1d = ys[:, 0] if ys.shape == depth.shape else ys[0, :]
        # Prefer axes that vary: x along columns, y along rows.
        if float(np.nanstd(xs[0, :])) >= float(np.nanstd(xs[:, 0])):
            xs_1d = xs[0, :]
        else:
            xs_1d = xs[:, 0]
        if float(np.nanstd(ys[:, 0])) >= float(np.nanstd(ys[0, :])):
            ys_1d = ys[:, 0]
        else:
            ys_1d = ys[0, :]
        xs, ys = np.asarray(xs_1d), np.asarray(ys_1d)

    epsg = 32618
    inp = (model_dir / "sfincs.inp").read_text()
    for line in inp.splitlines():
        if line.strip().startswith("epsg"):
            epsg = int(line.split("=")[1].strip())

    if xs.ndim != 1 or ys.ndim != 1:
        raise RuntimeError(f"Expected 1D x/y axes from SFINCS map (got {xs.shape}, {ys.shape})")
    if len(xs) != depth.shape[1] or len(ys) != depth.shape[0]:
        # Try transpose if axes swapped
        if len(xs) == depth.shape[0] and len(ys) == depth.shape[1]:
            depth = depth.T
        else:
            raise RuntimeError(
                f"Depth shape {depth.shape} incompatible with x={xs.shape} y={ys.shape}"
            )
    dx = float(np.median(np.diff(xs))) if len(xs) > 1 else 50.0
    dy = float(np.median(np.diff(ys))) if len(ys) > 1 else 50.0
    west = float(xs.min() - abs(dx) / 2)
    north = float(ys.max() + abs(dy) / 2)
    transform = from_origin(west, north, abs(dx), abs(dy))
    if dy > 0 and ys[0] < ys[-1]:
        depth = np.flipud(depth)

    out_tif.parent.mkdir(parents=True, exist_ok=True)
    tif_utm = out_tif.with_name(out_tif.stem + "_utm.tif")
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

    if ref_tif is not None and ref_tif.exists():
        with rasterio.open(ref_tif) as src:
            dst_shape = (src.height, src.width)
            dst_transform = src.transform
            dst_crs = src.crs
    else:
        # ~100 m display grid over the extent
        b = extent_bounds
        dst_shape = (
            max(32, int(round((b["ymax"] - b["ymin"]) / 0.001))),
            max(32, int(round((b["xmax"] - b["xmin"]) / 0.001))),
        )
        dst_transform = from_bounds(
            b["xmin"], b["ymin"], b["xmax"], b["ymax"], dst_shape[1], dst_shape[0]
        )
        dst_crs = "EPSG:4326"

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

    with rasterio.open(
        out_tif,
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

    vmax = float(np.nanpercentile(dest[np.isfinite(dest)], 98)) if np.isfinite(dest).any() else 0.5
    vmax = max(vmax, 0.05)
    cmap = colormaps["Blues"]
    norm = np.clip(np.nan_to_num(dest, nan=0.0) / vmax, 0, 1)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(
        np.isfinite(dest) & (dest > 0.005),
        np.clip(80 + norm * 175, 0, 255).astype(np.uint8),
        0,
    )
    Image.fromarray(rgba, "RGBA").save(out_png)

    meta = {
        "engine": ENGINE_ID,
        "engine_label": ENGINE_LABEL,
        "image": IMAGE,
        "label": label,
        "tif": str(out_tif),
        "png": out_png.name,
        "max_m": float(np.nanmax(dest)) if np.isfinite(dest).any() else None,
        "p50_m": float(np.nanpercentile(dest[np.isfinite(dest)], 50))
        if np.isfinite(dest).any()
        else None,
        "p90_m": float(np.nanpercentile(dest[np.isfinite(dest)], 90))
        if np.isfinite(dest).any()
        else None,
        "wet_fraction": float(np.mean(np.isfinite(dest) & (dest > 0.005))),
        "extent_bounds": extent_bounds,
        "forcing": "spatial_mrms_precip_2d_plus_drainage_sink",
        "role": "advanced_research_hydro",
        "primary": False,
        "official_nws": False,
        "decision_grade": False,
        "not_swmm": True,
        "enterprise": False,
        "hens": False,
        "source_nc": str(map_nc),
        "variable": var,
        "honesty": (
            "SFINCS Advanced research hydro — spatial MRMS + open drainage sink. "
            "NOT peer with primary HAND; NOT SWMM; NOT DEP; NOT NWS / NOT decision-grade."
        ),
    }
    out_meta.write_text(json.dumps(meta, indent=2))
    ds.close()
    return meta


def composite_nest_onto_coarse(
    coarse_tif: Path,
    nest_tif: Path,
    *,
    out_tif: Path,
    out_png: Path,
    out_meta: Path,
) -> dict[str, Any]:
    """Paste Queens nest depths onto metro coarse grid (research composite only)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import colormaps
    from PIL import Image
    from rasterio.warp import Resampling, reproject

    with rasterio.open(coarse_tif) as csrc:
        coarse = csrc.read(1).astype(np.float32)
        profile = csrc.profile.copy()
        dst_transform = csrc.transform
        dst_crs = csrc.crs
        dst_shape = coarse.shape

    nest_on_coarse = np.full(dst_shape, np.nan, dtype=np.float32)
    with rasterio.open(nest_tif) as nsrc:
        reproject(
            source=rasterio.band(nsrc, 1),
            destination=nest_on_coarse,
            src_transform=nsrc.transform,
            src_crs=nsrc.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )

    # Prefer nest where wet; else keep coarse.
    nest_wet = np.isfinite(nest_on_coarse) & (nest_on_coarse > 0.005)
    composite = coarse.copy()
    composite[nest_wet] = nest_on_coarse[nest_wet]

    out_tif.parent.mkdir(parents=True, exist_ok=True)
    profile.update(dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(out_tif, "w", **profile) as dst:
        dst.write(composite, 1)

    vmax = (
        float(np.nanpercentile(composite[np.isfinite(composite)], 98))
        if np.isfinite(composite).any()
        else 0.5
    )
    vmax = max(vmax, 0.05)
    cmap = colormaps["Blues"]
    norm = np.clip(np.nan_to_num(composite, nan=0.0) / vmax, 0, 1)
    rgba = (cmap(norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(
        np.isfinite(composite) & (composite > 0.005),
        np.clip(80 + norm * 175, 0, 255).astype(np.uint8),
        0,
    )
    Image.fromarray(rgba, "RGBA").save(out_png)

    meta = {
        "engine": ENGINE_ID,
        "engine_label": ENGINE_LABEL,
        "png": out_png.name,
        "tif": str(out_tif),
        "coarse_tif": str(coarse_tif),
        "nest_tif": str(nest_tif),
        "max_m": float(np.nanmax(composite)) if np.isfinite(composite).any() else None,
        "wet_fraction": float(np.mean(np.isfinite(composite) & (composite > 0.005))),
        "nest_cells_overwritten": int(np.count_nonzero(nest_wet)),
        "role": "advanced_research_hydro",
        "primary": False,
        "not_swmm": True,
        "official_nws": False,
        "decision_grade": False,
        "honesty": (
            "Metro nested SFINCS composite (100 m coarse + Queens 50 m nest). "
            "Advanced research hydro only — HAND remains primary. No SWMM."
        ),
    }
    out_meta.write_text(json.dumps(meta, indent=2))
    return meta
