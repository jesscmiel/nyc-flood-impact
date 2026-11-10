#!/usr/bin/env python3
"""Minimal STRATA → precip → Docker SFINCS → exposure intersect spike.

Research only — NOT official NWS. No Enterprise / HENS.
Uses a SCREAM sdecadal IC (not Ida). Prefer single-tile BF16 inference on
1×RTX 4090; optional Docker torchrun path is documented separately.

Environment:
  AUX_DATA_ROOT   — strata_v1 bundle (checkpoint, phis/sgh30/landfrac, latlon)
  SCREAM_MAIN_ZARR_PATH — default hf://datasets/nvidia/STRATA-SCREAM-sdecadal
  STRATA_REPO     — path to NVlabs/STRATA checkout (for imports / data_catalog)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.exposure.geopackage import intersect_depth_gpkg
from flood_risk.risk.depth_asset_tables import DEPTH_BANDS
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.extents import EXTENTS

ASSETS = FIGURES_DIR / "product_assets"
SPIKE_DIR = OUTPUTS_DIR / "strata_sfincs_spike"
IMAGE = "deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release"
DEM = PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif"
DEFAULT_AUX = PROJECT_ROOT / "data" / "raw" / "strata_v1"
DEFAULT_STRATA_REPO = Path("/home/jesscmiel/projects/STRATA")
NYC_LON, NYC_LAT = -73.94, 40.73  # South Queens-ish
NSIDE = 2048  # ne1024pg2


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


def _docker(cmd: list[str]) -> subprocess.CompletedProcess:
    full = ["sg", "docker", "-c", " ".join(shlex_quote(c) for c in cmd)]
    return subprocess.run(full, check=False, capture_output=True, text=True)


def _unstructured_to_faces_np(data: np.ndarray, ne: int = 1024, npg: int = 2) -> np.ndarray:
    """Match screamcast.cubesphere_transforms.unstructured_to_6faces (numpy)."""
    nside = ne * npg
    npts = nside * nside
    faces = data.reshape(6, npts)
    # reorder_cubesphere_to_2d: (ne, ne, npg, npg) -> (ne, npg, ne, npg) -> (nside, nside)
    x = faces.reshape(6, ne, ne, npg, npg)
    x = np.transpose(x, (0, 1, 3, 2, 4)).reshape(6, nside, nside)
    return x


def find_nyc_tile(
    latlon_path: Path, lon: float, lat: float, tile_size: int
) -> dict:
    """Locate cube-face tile containing (lon, lat) from latlon_ne1024pg2.nc."""
    import netCDF4 as nc

    with nc.Dataset(latlon_path) as ds:
        lats = np.asarray(ds.variables["lat"][:], dtype=np.float32)
        lons = np.asarray(ds.variables["lon"][:], dtype=np.float32)
    lon_q = lon % 360.0
    lons_n = np.where(lons < 0, lons + 360.0, lons)
    lat_f = _unstructured_to_faces_np(lats)
    lon_f = _unstructured_to_faces_np(lons_n)
    dlat = lat_f - lat
    dlon = ((lon_f - lon_q + 180.0) % 360.0) - 180.0
    dist2 = dlat * dlat + dlon * dlon
    face, y, x = [int(i) for i in np.unravel_index(int(np.argmin(dist2)), dist2.shape)]
    x0 = max(0, min(x - tile_size // 2, NSIDE - tile_size))
    y0 = max(0, min(y - tile_size // 2, NSIDE - tile_size))
    ncol = face * (NSIDE * NSIDE) + y * NSIDE + x  # face-grid index, not raw SCRIP
    return {
        "ncol_face_rowmajor": ncol,
        "face": face,
        "x": x,
        "y": y,
        "x0": x0,
        "y0": y0,
        "tile_size": int(tile_size),
        "lat": float(lat_f[face, y, x]),
        "lon": float(lon_f[face, y, x]),
        "query_lat": lat,
        "query_lon": lon,
        "dist_deg": float(np.sqrt(dist2[face, y, x])),
    }


def m_s_to_mm_hr(flux_m_s: float) -> float:
    return float(flux_m_s) * 1000.0 * 3600.0


def run_single_tile_infer(
    aux: Path,
    strata_repo: Path,
    tile: dict,
    n_steps: int,
    initial_time: str,
    out_dir: Path,
) -> dict:
    """BF16 single-tile STRATA rollout (4090-friendly)."""
    os.environ["AUX_DATA_ROOT"] = str(aux)
    os.environ.setdefault(
        "SCREAM_MAIN_ZARR_PATH", "hf://datasets/nvidia/STRATA-SCREAM-sdecadal"
    )
    os.environ.setdefault("SCREAM_AUX_ZARR_PATH", os.environ["SCREAM_MAIN_ZARR_PATH"])
    sys.path.insert(0, str(strata_repo))

    import torch
    from data_catalog import scream
    from screamcast.earth2studio_wrappers import ScreamcastModel

    ckpt = aux / "checkpoints" / "strata_v1.pth"
    if not ckpt.exists():
        raise FileNotFoundError(ckpt)

    t_load0 = time.time()
    vram0 = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else None
    model = ScreamcastModel.from_checkpoint(str(ckpt), bf16=True)
    model = model.cuda()
    model.eval()
    tile_size = tile["tile_size"]
    model.set_tile_size(tile_size)
    # Eager on 4090 — compile can thrash VRAM during first step
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

    in_coords = dict(model.input_coords())
    ds = scream()
    t0 = np.datetime64(initial_time)
    face = np.array([tile["face"]])
    xs = np.arange(tile["x0"], tile["x0"] + tile_size)
    ys = np.arange(tile["y0"], tile["y0"] + tile_size)
    fetch_coords = {
        "time": np.array([t0]),
        "variable": list(in_coords["variable"]),
        "face": face,
        "x": xs,
        "y": ys,
    }
    print(f"Fetching IC tile face={tile['face']} x0={tile['x0']} y0={tile['y0']} …")
    ic_da = ds(fetch_coords)
    x_np = ic_da.values  # (1, C, 1, tile, tile)
    print(f"IC shape={x_np.shape} load_s={time.time() - t_load0:.1f}")

    x_tensor = torch.from_numpy(x_np).cuda()
    coords_model = dict(in_coords)
    coords_model["face"] = face
    coords_model["batch"] = np.empty(1)
    coords_model["time"] = np.array([t0])
    coords_model["x"] = xs
    coords_model["y"] = ys

    precip_steps: list[dict] = []
    peak_vram_mb = 0.0
    with torch.inference_mode():
        iterator = model.create_iterator(x_tensor, coords_model)
        next(iterator)  # lead 0
        for step in range(n_steps):
            out_tensor, out_coords = next(iterator)
            names = list(out_coords["variable"])
            if "precip_liq_surf_mass_flux" not in names:
                raise RuntimeError(f"precip_liq missing in outputs: {names[:20]}…")
            vi = names.index("precip_liq_surf_mass_flux")
            arr = out_tensor[0, vi, 0].float().cpu().numpy()
            # clip fill / neg
            arr = np.where(np.isfinite(arr) & (arr < 1e10) & (arr > 0), arr, 0.0)
            mean_flux = float(arr.mean())
            max_flux = float(arr.max())
            precip_steps.append(
                {
                    "step": step + 1,
                    "lead_min": (step + 1) * 10,
                    "mean_m_s": mean_flux,
                    "max_m_s": max_flux,
                    "mean_mm_hr": m_s_to_mm_hr(mean_flux),
                    "max_mm_hr": m_s_to_mm_hr(max_flux),
                }
            )
            if torch.cuda.is_available():
                peak_vram_mb = max(
                    peak_vram_mb,
                    (torch.cuda.max_memory_allocated() / (1024**2)),
                )
            print(
                f"step {step + 1}/{n_steps} precip mean={m_s_to_mm_hr(mean_flux):.3f} mm/hr "
                f"max={m_s_to_mm_hr(max_flux):.3f} mm/hr"
            )

    # Persist last-step precip tile
    out_dir.mkdir(parents=True, exist_ok=True)
    last = out_tensor[0, vi, 0].float().cpu().numpy()
    last = np.where(np.isfinite(last) & (last < 1e10) & (last > 0), last, 0.0)
    np.save(out_dir / "precip_liq_last_tile_m_s.npy", last.astype(np.float32))

    mean_mm_hr = float(np.mean([p["mean_mm_hr"] for p in precip_steps]))
    max_mm_hr = float(np.max([p["max_mm_hr"] for p in precip_steps]))
    result = {
        "mode": "single_tile_bf16",
        "initial_time": initial_time,
        "tile": tile,
        "n_steps": n_steps,
        "precip_steps": precip_steps,
        "mean_mm_hr": mean_mm_hr,
        "max_mm_hr": max_mm_hr,
        "peak_vram_alloc_mb": peak_vram_mb,
        "cuda_mem_free_after_mb": (torch.cuda.mem_get_info()[0] / (1024**2))
        if torch.cuda.is_available()
        else None,
        "vram_free_before_mb": (vram0 / (1024**2)) if vram0 is not None else None,
        "checkpoint": str(ckpt),
        "honesty": (
            "STRATA v1 single-tile rollout from SCREAM sdecadal IC "
            f"{initial_time}. Not Ida; not FCN-initialized; research only."
        ),
    }
    (out_dir / "strata_infer_meta.json").write_text(json.dumps(result, indent=2))
    return result


def build_and_run_sfincs(precip_mm_hr: float, hours: float, model_dir: Path) -> dict:
    """HydroMT Queens model + Docker SFINCS with uniform STRATA-derived rate."""
    import pandas as pd

    _orig = pd.date_range

    def _date_range(*args, **kwargs):
        freq = kwargs.get("freq")
        if isinstance(freq, str) and freq.endswith("T") and not freq.endswith("min"):
            kwargs["freq"] = freq[:-1] + "min"
        return _orig(*args, **kwargs)

    pd.date_range = _date_range  # type: ignore[assignment]

    from hydromt_sfincs import SfincsModel

    if model_dir.exists():
        shutil.rmtree(model_dir)
    model_dir.mkdir(parents=True)

    b = EXTENTS["south_queens"]["bounds"]
    region = {"bbox": [b["xmin"], b["ymin"], b["xmax"], b["ymax"]]}
    # Synthetic calendar window (not Ida): 2020-10-13 matching SCREAM IC day
    tref = "20201013 000000"
    # hours of forcing for a visible inundation demo (STRATA only produced n_steps*10min)
    tstop_h = max(hours, 1.0)
    # encode stop as HHMMSS from midnight
    stop_h = int(tstop_h)
    stop_m = int(round((tstop_h - stop_h) * 60))
    tstop = f"20201013 {stop_h:02d}{stop_m:02d}00"

    sf = SfincsModel(root=str(model_dir), mode="w+")
    sf.setup_grid_from_region(region=region, res=50, crs="utm")
    sf.setup_config(
        tref=tref,
        tstart=tref,
        tstop=tstop,
        dtout=3600,
        dthisout=600,
        dtmaxout=int(tstop_h * 3600),
        alpha=0.5,
        theta=1.0,
        manning=0.04,
        huthresh=0.01,
    )
    sf.setup_dep(datasets_dep=[{"elevtn": str(DEM), "reproj_method": "bilinear"}])
    sf.setup_mask_active(zmin=-5.0)
    rate = max(float(precip_mm_hr), 0.05)
    sf.setup_precip_forcing(magnitude=rate)
    sf.write()

    meta = {
        "model_dir": str(model_dir),
        "extent": "south_queens",
        "res_m": 50,
        "precip_mm_hr": rate,
        "precip_source": "strata_v1_scream_ic_tile_mean",
        "tstart": tref,
        "tstop": tstop,
        "hours": tstop_h,
        "enterprise": False,
        "hens": False,
        "official_nws": False,
        "honesty": (
            "Uniform precip from STRATA tile-mean liquid precip flux. "
            "SCREAM sdecadal weather, not Ida observations."
        ),
    }
    (model_dir / "build_meta.json").write_text(json.dumps(meta, indent=2))

    pull = _docker(["docker", "pull", IMAGE])
    run = _docker(["docker", "run", "--rm", "-v", f"{model_dir.resolve()}:/data", IMAGE])
    log = {
        "image": IMAGE,
        "pull_returncode": pull.returncode,
        "run_returncode": run.returncode,
        "run_stdout_tail": (run.stdout or "")[-3000:],
        "run_stderr_tail": (run.stderr or "")[-3000:],
        "files_after": sorted(p.name for p in model_dir.iterdir()),
    }
    (model_dir / "docker_run_log.json").write_text(json.dumps(log, indent=2))
    if run.returncode != 0:
        raise RuntimeError(f"SFINCS docker failed: {run.stderr or run.stdout}")
    meta["docker"] = log
    return meta


def export_depth(model_dir: Path, out_stem: str = "depth_sfincs_strata_queens") -> dict:
    import rasterio
    import xarray as xr
    from rasterio.crs import CRS
    from rasterio.transform import from_bounds, from_origin
    from rasterio.warp import Resampling, reproject

    ncs = list(model_dir.glob("*.nc"))
    if not ncs:
        raise FileNotFoundError(f"No NetCDF in {model_dir}")
    map_nc = next((p for p in ncs if "map" in p.name.lower()), ncs[0])
    ds = xr.open_dataset(map_nc)
    var = next(
        (n for n in ("hmax", "zsmax", "h", "waterdepth", "depth") if n in ds),
        None,
    )
    if var is None:
        var = next(n for n, da in ds.data_vars.items() if da.ndim >= 2)
    da = ds[var]
    if "timemax" in da.dims:
        da = da.isel(timemax=-1)
    elif "time" in da.dims:
        da = da.max("time")
    depth = np.asarray(da.values, dtype=np.float32)
    depth = np.squeeze(depth)
    depth = np.where(np.isfinite(depth) & (depth > 0), depth, np.nan)
    xs = np.asarray(da["x"].values)
    ys = np.asarray(da["y"].values)
    # SFINCS map NetCDF often stores 2-D meshgrid x/y
    if xs.ndim == 2:
        xs = xs[0, :]
    if ys.ndim == 2:
        ys = ys[:, 0]
    epsg = 32618
    for line in (model_dir / "sfincs.inp").read_text().splitlines():
        if line.strip().startswith("epsg"):
            epsg = int(line.split("=")[1].strip())
    dx = float(np.median(np.diff(xs))) if len(xs) > 1 else 50.0
    dy = float(np.median(np.diff(ys))) if len(ys) > 1 else 50.0
    if abs(dx) < 1e-6 or abs(dy) < 1e-6:
        raise RuntimeError(f"Degenerate grid spacing dx={dx} dy={dy}")
    transform = from_origin(
        float(np.min(xs) - abs(dx) / 2),
        float(np.max(ys) + abs(dy) / 2),
        abs(dx),
        abs(dy),
    )
    if dy > 0 and ys[0] < ys[-1]:
        depth = np.flipud(depth)

    out_dir = PROCESSED_DIR / "inundation"
    out_dir.mkdir(parents=True, exist_ok=True)
    tif_utm = out_dir / f"{out_stem}_utm.tif"
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

    b = EXTENTS["south_queens"]["bounds"]
    ref = out_dir / "depth_sfincs_queens_ida_m.tif"
    if ref.exists():
        with rasterio.open(ref) as src:
            dst_shape = (src.height, src.width)
            dst_transform = src.transform
            dst_crs = src.crs
    else:
        dst_shape = (217, 481)
        dst_transform = from_bounds(b["xmin"], b["ymin"], b["xmax"], b["ymax"], dst_shape[1], dst_shape[0])
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
    tif = out_dir / f"{out_stem}_m.tif"
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

    finite = dest[np.isfinite(dest)]
    meta = {
        "tif": str(tif),
        "max_m": float(np.nanmax(finite)) if finite.size else None,
        "p50_m": float(np.nanpercentile(finite, 50)) if finite.size else None,
        "p90_m": float(np.nanpercentile(finite, 90)) if finite.size else None,
        "wet_fraction_gt_5cm": float(np.mean(np.isfinite(dest) & (dest > 0.05))),
        "variable": var,
        "source_nc": str(map_nc),
        "extent": "south_queens",
        "official_nws": False,
        "enterprise": False,
        "hens": False,
    }
    (out_dir / f"{out_stem}_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / f"{out_stem}_meta.json").write_text(json.dumps(meta, indent=2))
    ds.close()
    return meta


def intersect_assets(depth_tif: Path, out_json: Path) -> dict:
    gpkg = ASSETS / "exposure_citywide.gpkg"
    if not gpkg.exists():
        raise FileNotFoundError(gpkg)
    inter = intersect_depth_gpkg(gpkg, depth_tif, DEPTH_BANDS)
    inter["bands"] = DEPTH_BANDS
    inter["honesty"] = (
        "Asset intersects on STRATA→SFINCS research depth. Not calibrated inundation."
    )
    out_json.write_text(json.dumps(inter, indent=2))
    (ASSETS / out_json.name).write_text(json.dumps(inter, indent=2))
    return inter


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aux", type=Path, default=Path(os.environ.get("AUX_DATA_ROOT", DEFAULT_AUX)))
    ap.add_argument("--strata-repo", type=Path, default=Path(os.environ.get("STRATA_REPO", DEFAULT_STRATA_REPO)))
    ap.add_argument("--n-steps", type=int, default=2)
    ap.add_argument("--tile-size", type=int, default=64, help="64 safer on 24GB; 128 is production FT")
    ap.add_argument("--initial-time", default="2020-10-13T00:00:00")
    ap.add_argument("--sfincs-hours", type=float, default=3.0, help="SFINCS window with uniform rate")
    ap.add_argument("--precip-mm-hr", type=float, default=None, help="Skip infer; force this rate")
    ap.add_argument("--skip-infer", action="store_true")
    ap.add_argument("--skip-sfincs", action="store_true")
    args = ap.parse_args()

    SPIKE_DIR.mkdir(parents=True, exist_ok=True)
    latlon = args.aux / "latlon_ne1024pg2.nc"
    summary: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if args.precip_mm_hr is not None:
        infer = {
            "mode": "manual_override",
            "mean_mm_hr": args.precip_mm_hr,
            "max_mm_hr": args.precip_mm_hr,
        }
    elif args.skip_infer:
        meta_path = SPIKE_DIR / "strata_infer_meta.json"
        infer = json.loads(meta_path.read_text())
    else:
        if not latlon.exists():
            raise SystemExit(
                f"BLOCKER: {latlon} missing. Run STRATA data_prep/scrip_generation "
                "(generate_exodus → scrip_convert → derive_latlon) into AUX_DATA_ROOT."
            )
        tile = find_nyc_tile(latlon, NYC_LON, NYC_LAT, args.tile_size)
        (SPIKE_DIR / "nyc_tile.json").write_text(json.dumps(tile, indent=2))
        print(json.dumps(tile, indent=2))
        infer = run_single_tile_infer(
            args.aux, args.strata_repo, tile, args.n_steps, args.initial_time, SPIKE_DIR
        )

    summary["infer"] = {k: infer[k] for k in infer if k != "precip_steps"}
    summary["infer"]["precip_steps"] = infer.get("precip_steps")
    rate = float(infer["mean_mm_hr"])
    print(f"Using precip rate {rate:.4f} mm/hr for SFINCS")

    if not args.skip_sfincs:
        model_dir = SPIKE_DIR / "sfincs_model"
        sf_meta = build_and_run_sfincs(rate, args.sfincs_hours, model_dir)
        depth = export_depth(model_dir)
        inter = intersect_assets(
            Path(depth["tif"]), SPIKE_DIR / "strata_exposure_intersects.json"
        )
        summary["sfincs"] = sf_meta
        summary["depth"] = depth
        summary["exposure"] = inter

    summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (SPIKE_DIR / "spike_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
