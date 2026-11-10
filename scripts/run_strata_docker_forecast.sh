#!/usr/bin/env bash
# STRATA Docker 2-step forecast smoke (global tiles on mounted GPUs).
# Research only — SCREAM sdecadal IC, not Ida. NOT official NWS.
set -euo pipefail

ROOT="${STRATA_REPO:-/home/jesscmiel/projects/STRATA}"
AUX="${AUX_DATA_ROOT:-/home/jesscmiel/projects/nyc-flood-impact/data/raw/strata_v1}"
OUT="${OUTPUT:-/home/jesscmiel/projects/nyc-flood-impact/outputs/strata_sfincs_spike/strata_v1_2step}"
IMAGE="${STRATA_IMAGE:-strata}"
NPROC="${NPROC_PER_NODE:-1}"
N_STEPS="${N_STEPS:-2}"
TILE="${TILE_SIZE:-64}"

export SCREAM_MAIN_ZARR_PATH="${SCREAM_MAIN_ZARR_PATH:-hf://datasets/nvidia/STRATA-SCREAM-sdecadal}"
export SCREAM_AUX_ZARR_PATH="${SCREAM_AUX_ZARR_PATH:-$SCREAM_MAIN_ZARR_PATH}"

mkdir -p "$(dirname "$OUT")"

# Single-GPU 4090: tile 64, eager, regional-means only. May still OOM on global
# state; prefer scripts/run_strata_sfincs_spike.py single-tile path on this host.
sg docker -c "docker run --rm --gpus all \
  -e AUX_DATA_ROOT=/aux \
  -e SCREAM_MAIN_ZARR_PATH=$SCREAM_MAIN_ZARR_PATH \
  -e SCREAM_AUX_ZARR_PATH=$SCREAM_AUX_ZARR_PATH \
  -e PYTHONPATH=/workspace \
  -e TORCH_COMPILE_DISABLE=1 \
  -e PYTHONUNBUFFERED=1 \
  -v $ROOT:/workspace \
  -v $AUX:/aux \
  -v $(dirname "$OUT"):/out \
  -w /workspace \
  $IMAGE \
  torchrun --nproc_per_node=$NPROC scripts/ace/run_screamcast_nudged.py \
    --run-name strata_v1_nyc_spike \
    --checkpoint /aux/checkpoints/strata_v1.pth \
    --forecast-model screamcast \
    --correction none \
    --n-steps $N_STEPS \
    --tile-size $TILE \
    --halo-width 16 \
    --halo-adjoint \
    --no-halo-adjoint-cross-face \
    --inference-batch-size 1 \
    --tile-jitter 4 \
    --tile-jitter-mode cycle16 \
    --sht-omega-lmax 3 \
    --output-variables precip_liq_surf_mass_flux T_2m \
    --no-zarr-output \
    --initial-time 2020-10-13T00:00:00 \
    /out/$(basename "$OUT")"
