# SFINCS / LISFLOOD-FP — user install guide

**Research stack only.** No Earth2Studio Enterprise / HENS.  
This agent **did not** run SFINCS or LISFLOOD-FP on the NYC case study — only a HydroMT **schema** under `outputs/sfincs_spike_queens/` exists. Do not treat that folder as a completed inundation run.

Current MVP inundation remains **pysheds** HAND/bathtub. See `docs/inundation-engine-spike.md`.

---

## SFINCS (Deltares)

### What you need

| Piece | Role |
| --- | --- |
| **SFINCS executable** | Runs the hydrodynamic model |
| **HydroMT-SFINCS** | Builds `sfincs.inp` + grids from DEM/forcing (Python) |

### Linux / Mac / HPC — Docker (recommended)

Official Docker Hub: https://hub.docker.com/r/deltares/sfincs-cpu

```bash
# Pull a tagged open release (example: Dollerup 2024)
docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release

# Or latest tag
docker pull deltares/sfincs-cpu

# Run against an absolute path that contains sfincs.inp (+ dep/forcing files)
# Linux/Mac path form:
docker run --rm -v /ABS/PATH/TO/MODEL:/data deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release
```

Notes from Deltares docs:

- Mount path must be **absolute**, not relative.
- On HPC without Docker, convert the image with **Apptainer/Singularity** (`apptainer pull docker://deltares/sfincs-cpu:…`).
- Dedicated Linux bare-metal builds are not generally published; Docker/Apptainer is the supported Linux path.

### Windows — precompiled EXE

Download from Deltares: https://download.deltares.nl/en/sfincs (or https://download.deltares.nl/sfincs).  
Accept their license terms when downloading. Place `sfincs.exe` on `PATH` or run from the model directory.

### HydroMT-SFINCS (model builder)

```bash
# Recommended: conda-forge env
mamba env create -f https://raw.githubusercontent.com/Deltares/hydromt_sfincs/main/environment.yml
conda activate hydromt-sfincs

# Or into an existing env
mamba install -c conda-forge hydromt_sfincs
# pip alternative (already used in this repo's .venv for schema spike):
pip install 'hydromt-sfincs>=1.2'
```

Docs: https://deltares.github.io/hydromt_sfincs/  

### Wire into this repo (after you have a binary/container)

1. Build/complete a citywide or borough model (DEM + Ida precip forcing) with HydroMT-SFINCS.  
2. Run via Docker as above **or** `sfincs` on PATH.  
3. Export max-depth GeoTIFF → drop into `data/processed/inundation/` and re-run `scripts/build_risk_tables.py`.  
4. Keep UI labels: research / not NWS / not decision-grade.

This cloud/agent environment: `hydromt-sfincs` ✅ schema; Docker SFINCS ✅ run against Queens/Ida model — see **`docs/sfincs-docker-run.md`** for exact commands and depth outputs. No Enterprise / HENS.

---

## LISFLOOD-FP

No pip wheel. Compile from source (CPU) or use Zenodo release archives.

### Dependencies (Ubuntu example)

```bash
sudo apt update
sudo apt install -y cmake g++ libnuma-dev libnetcdf-dev
# Optional GPU solvers: CUDA toolkit
```

### Build (LISFLOOD-FP 8.x)

```bash
# Option A — Zenodo 8.3 source zip
# https://zenodo.org/records/13121119
unzip LISFLOOD-FP-8.3.zip
cd LISFLOOD-FP-trunk   # or the extracted source dir

cmake -S . -B build
cmake --build build -j"$(nproc)"
# binary: build/lisflood
export PATH="$PWD/build:$PATH"
```

Upstream compile notes: https://www.seamlesswave.com/compile_lin.html  

GitHub mirrors vary (e.g. SEAMLESS-WAVE / community 8.3 forks). Prefer the Zenodo DOI package for a pinned research build.

### Run (user)

Prepare LISFLOOD-FP parameter/DEM/rain files per their docs, then:

```bash
lisflood your_case.par
```

Convert depth outputs to GeoTIFF and feed `flood_risk` / `build_risk_tables.py` the same way as SFINCS.

---

## Honesty checklist

- [ ] Do **not** claim a SFINCS/LISFLOOD run completed in this repo unless `outputs/` contains solver logs + depth rasters you produced.  
- [ ] Schema-only HydroMT folders ≠ inundation results.  
- [ ] pysheds remains the documented MVP engine until a binary/container run is verified.  
- [ ] No Enterprise / HENS.
