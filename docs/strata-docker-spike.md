# STRATA Docker spike → SFINCS → assets

**Host:** `earth2-nyc` (RTX 4090 ~24 GB).  
**Result:** **Success** (methods demo). SCREAM sdecadal IC → 2-step single-tile STRATA → Queens Docker SFINCS → exposure GPKG.  
**Not Ida.** Ida stays on MRMS/FCN. No Enterprise / HENS. Research only — NOT official NWS.

## Key numbers

| Metric | Value |
| --- | --- |
| IC time | `2020-10-13T00:00:00` (sdecadal; streamed `hf://datasets/nvidia/STRATA-SCREAM-sdecadal`) |
| NYC tile | face **3**, origin `(1357, 1944)`, size **64²** |
| STRATA steps | 2 × 10 min (BF16, eager) |
| Peak VRAM alloc | **~4.05 GB** (fits easily on 4090) |
| Wall (infer) | ~838 s (dominated by HF IC chunk stream ~14 min) |
| Tile-mean precip | **0.029 mm/hr** (mostly dry) |
| Tile-max precip | **7.15 mm/hr** |
| Wet-cell mean (>0.01 mm/hr) | **0.833 mm/hr** ← SFINCS forcing |
| SFINCS window | 3 h @ 0.833 mm/hr uniform (Queens 50 m) |
| Peak depth | **~2.80 m** |
| p50 / p90 depth | ~1.25 m / ~1.62 m |
| Wet fraction (>5 cm) | **~0.099** |
| Roads wet / hazard ≥15 cm | **13 / 13** (of 2200) |
| Stations / facilities wet | **0 / 0** |

Honesty: SCREAM Oct-2020-SST / 1994-atmosphere weather ≠ Ida; uniform wet-cell mean forcing is a coupling demo, not calibrated inundation.

## Commands that worked

### 1. AUX + latlon

```bash
hf download nvidia/strata --local-dir data/raw/strata_v1
cp /path/to/STRATA/data/scream_vertical_coordinate.nc data/raw/strata_v1/
# no-halo SCRIP only (halo skipped for single-tile):
cd /path/to/STRATA
python data_prep/scrip_generation/generate_exodus_meshes.py --res 1024 --np 2 --halo 0 --out-dir $AUX
python data_prep/scrip_generation/scrip_convert.py --in-exodus $AUX/ne1024pg2.g
python data_prep/scrip_generation/derive_latlon.py --in-scrip $AUX/ne1024pg2_scrip.nc --out $AUX/latlon_ne1024pg2.nc
```

### 2. Docker image (Ada / sm_89)

```bash
cd /path/to/STRATA
sg docker -c 'docker pull nvcr.io/nvidia/pytorch:26.09-py3'
sg docker -c 'docker build -f docker/Dockerfile --build-arg CUDA_ARCH=8.9 -t strata .'
```

Host `pip install screamcast` failed: system `nvcc` is CUDA **11.5** vs torch **13.x** (`earth2grid` build). Use the NGC image.

### 3. Single-tile infer (preferred on 1×4090)

```bash
sg docker -c "docker run --rm --gpus all --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -e AUX_DATA_ROOT=/aux \
  -e SCREAM_MAIN_ZARR_PATH=hf://datasets/nvidia/STRATA-SCREAM-sdecadal \
  -e SCREAM_AUX_ZARR_PATH=hf://datasets/nvidia/STRATA-SCREAM-sdecadal \
  -e TORCH_COMPILE_DISABLE=1 -e PYTHONPATH=/workspace \
  -v $STRATA:/workspace -v $PWD/data/raw/strata_v1:/aux \
  -v $PWD/outputs/strata_sfincs_spike:/out -v $PWD:/nfi \
  -w /workspace strata \
  bash -lc 'git config --global --add safe.directory /workspace; pip install -q -e . --no-deps && \
    python /nfi/scripts/strata_tile_infer.py --aux /aux --strata-repo /workspace --out-dir /out \
      --face 3 --x0 1357 --y0 1944 --tile-size 64 --n-steps 2 --initial-time 2020-10-13T00:00:00'"
```

### 4. SFINCS + assets

```bash
# wet-cell mean rate from last precip tile (see precip_forcing_choice.json)
.venv/bin/python scripts/run_strata_sfincs_spike.py --precip-mm-hr 0.833 --sfincs-hours 3
```

Optional global Docker `torchrun` wrapper: `scripts/run_strata_docker_forecast.sh` (likely OOM on one 4090).

## Artifacts

| Artifact | Path |
| --- | --- |
| Spike summary | `outputs/strata_sfincs_spike/spike_summary.json` (also `figures/product_assets/strata_spike_summary.json`) |
| Infer meta | `outputs/strata_sfincs_spike/strata_infer_meta.json` |
| Precip tile | `outputs/strata_sfincs_spike/precip_liq_last_tile_m_s.npy` |
| Forcing choice | `outputs/strata_sfincs_spike/precip_forcing_choice.json` |
| SFINCS model | `outputs/strata_sfincs_spike/sfincs_model/` |
| Depth GeoTIFF | `data/processed/inundation/depth_sfincs_strata_queens_m.tif` |
| Exposure JSON | `figures/product_assets/strata_exposure_intersects.json` |
| NYC tile | `outputs/strata_sfincs_spike/nyc_tile.json` |

Large AUX (`data/raw/strata_v1/`) is gitignored (checkpoint + SCRIP).

## Blockers cleared / remaining

| Item | Status |
| --- | --- |
| SCREAM IC | OK via HF stream |
| STRATA Docker + NATTEN Ada | OK (`strata:latest`) |
| 4090 VRAM for tile-64 | OK (~4 GB) |
| Ida SCREAM IC | Still blocked (use MRMS/FCN path) |
| FCN→STRATA IC | Still research-only |
| Spatial SFINCS precip | Still uniform magnitude |
| Host pip / CUDA 11.5 | Still blocked without CUDA 12+/13 toolkit |

## Next step

Cache a local one-frame IC Zarr for the NYC face to cut the ~14 min HF fetch; optionally wire spatial precip fields into HydroMT; keep Ida on MRMS/FCN.
