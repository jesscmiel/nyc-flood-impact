#!/usr/bin/env python3
"""Single-tile STRATA precip rollout (Docker / screamcast env).

Research only — SCREAM sdecadal IC, not Ida. NOT official NWS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch


def m_s_to_mm_hr(flux_m_s: float) -> float:
    return float(flux_m_s) * 1000.0 * 3600.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aux", type=Path, required=True)
    ap.add_argument("--strata-repo", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--face", type=int, default=3)
    ap.add_argument("--x0", type=int, default=1357)
    ap.add_argument("--y0", type=int, default=1944)
    ap.add_argument("--tile-size", type=int, default=64)
    ap.add_argument("--n-steps", type=int, default=2)
    ap.add_argument("--initial-time", default="2020-10-13T00:00:00")
    args = ap.parse_args()

    os.environ["AUX_DATA_ROOT"] = str(args.aux)
    os.environ.setdefault(
        "SCREAM_MAIN_ZARR_PATH", "hf://datasets/nvidia/STRATA-SCREAM-sdecadal"
    )
    os.environ.setdefault("SCREAM_AUX_ZARR_PATH", os.environ["SCREAM_MAIN_ZARR_PATH"])
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    sys.path.insert(0, str(args.strata_repo))

    from data_catalog import scream
    from screamcast.earth2studio_wrappers import ScreamcastModel

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = args.aux / "checkpoints" / "strata_v1.pth"
    t0_wall = time.time()
    free0, total = torch.cuda.mem_get_info()
    print(f"GPU free/total MB: {free0/1e6:.0f}/{total/1e6:.0f}")

    model = ScreamcastModel.from_checkpoint(str(ckpt), bf16=True)
    model = model.cuda().eval()
    model.set_tile_size(args.tile_size)

    in_coords = dict(model.input_coords())
    ds = scream()
    t0 = np.datetime64(args.initial_time)
    face = np.array([args.face])
    xs = np.arange(args.x0, args.x0 + args.tile_size)
    ys = np.arange(args.y0, args.y0 + args.tile_size)
    print(f"Fetching IC face={args.face} x0={args.x0} y0={args.y0} size={args.tile_size}")
    ic_da = ds(
        {
            "time": np.array([t0]),
            "variable": list(in_coords["variable"]),
            "face": face,
            "x": xs,
            "y": ys,
        }
    )
    x_np = ic_da.values
    print(f"IC shape={x_np.shape} fetch_s={time.time()-t0_wall:.1f}")

    x_tensor = torch.from_numpy(x_np).cuda()
    coords_model = dict(in_coords)
    coords_model["face"] = face
    coords_model["batch"] = np.empty(1)
    coords_model["time"] = np.array([t0])
    coords_model["x"] = xs
    coords_model["y"] = ys

    precip_steps = []
    last_arr = None
    with torch.inference_mode():
        it = model.create_iterator(x_tensor, coords_model)
        next(it)
        for step in range(args.n_steps):
            out_tensor, out_coords = next(it)
            names = list(out_coords["variable"])
            vi = names.index("precip_liq_surf_mass_flux")
            arr = out_tensor[0, vi, 0].float().cpu().numpy()
            arr = np.where(np.isfinite(arr) & (arr < 1e10) & (arr > 0), arr, 0.0)
            last_arr = arr
            mean_flux, max_flux = float(arr.mean()), float(arr.max())
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
            print(
                f"step {step+1}/{args.n_steps} "
                f"mean={m_s_to_mm_hr(mean_flux):.4f} mm/hr "
                f"max={m_s_to_mm_hr(max_flux):.4f} mm/hr "
                f"alloc_mb={torch.cuda.max_memory_allocated()/1e6:.0f}"
            )

    np.save(args.out_dir / "precip_liq_last_tile_m_s.npy", last_arr.astype(np.float32))
    mean_mm_hr = float(np.mean([p["mean_mm_hr"] for p in precip_steps]))
    result = {
        "mode": "single_tile_bf16_docker",
        "initial_time": args.initial_time,
        "tile": {
            "face": args.face,
            "x0": args.x0,
            "y0": args.y0,
            "tile_size": args.tile_size,
        },
        "n_steps": args.n_steps,
        "precip_steps": precip_steps,
        "mean_mm_hr": mean_mm_hr,
        "max_mm_hr": float(np.max([p["max_mm_hr"] for p in precip_steps])),
        "peak_vram_alloc_mb": torch.cuda.max_memory_allocated() / (1024**2),
        "cuda_mem_free_after_mb": torch.cuda.mem_get_info()[0] / (1024**2),
        "vram_free_before_mb": free0 / (1024**2),
        "wall_s": time.time() - t0_wall,
        "checkpoint": str(ckpt),
        "honesty": (
            "STRATA v1 single-tile BF16 rollout from SCREAM sdecadal IC "
            f"{args.initial_time}. Not Ida; not FCN-initialized; research only."
        ),
    }
    (args.out_dir / "strata_infer_meta.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
