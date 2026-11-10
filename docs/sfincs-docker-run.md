# SFINCS Docker run — South Queens / Ida

**No Enterprise / HENS. Research only — NOT official NWS.**

## Exact Docker commands used

These are the commands that actually ran (exit 0). Prefer `sg docker` if your shell session does not yet have the `docker` group:

```bash
sg docker -c 'docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'

sg docker -c 'docker run --rm -v /home/jesscmiel/projects/nyc-flood-impact/outputs/sfincs_queens_ida:/data deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'
```

Equivalent without `sg` (once `docker` group is active in the session):

```bash
docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release
docker run --rm -v "$PWD/outputs/sfincs_queens_ida:/data" deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release
```

- Image digest (this machine): `sha256:20eec911fd32c90876944566fbab3a89d127a550255451dcd3c1e590817b2691`
- Logged copy: `outputs/sfincs_queens_docker_commands.txt`
- Full pull/run log: `outputs/sfincs_queens_docker_log.json`

## One-shot rebuild + run

```bash
.venv/bin/python scripts/build_and_run_sfincs_queens.py
```

This rebuilds the HydroMT-SFINCS model under `outputs/sfincs_queens_ida/`, runs the Docker commands above, and exports depth GeoTIFF + product PNG/meta + manifest keys.

## Model

- HydroMT-SFINCS `1.2.2` → `outputs/sfincs_queens_ida/`
- DEM: USGS citywide clipped to South Queens bbox
- Forcing: **uniform** precip **~10.27 mm/hr** = Ida MRMS storm-total mean / 12 h (not spatially varying radar)
- Window: 2021-09-01 12Z → 2021-09-02 00Z
- Pandas note: HydroMT 1.2.x `freq="10T"` is monkeypatched to `10min` for pandas 2.2+

## Outputs

| Artifact | Path |
| --- | --- |
| Depth GeoTIFF (WGS84) | `data/processed/inundation/depth_sfincs_queens_ida_m.tif` |
| PNG overlay | `figures/product_assets/depth_sfincs_queens_ida_m.png` |
| Meta | `figures/product_assets/depth_sfincs_queens_ida_meta.json` |
| Map NetCDF (local) | `outputs/sfincs_queens_ida/sfincs_map.nc` |

Research stats (this run):

- max depth ≈ **3.76 m**
- p50 ≈ **0.048 m**, p90 ≈ **0.74 m**
- wet fraction (>5 cm) ≈ **0.49**

## vs pysheds (product map)

Toggles on `figures/product_map.html` (South Queens extent):

- **Queens pysheds depth** — HAND/bathtub from MRMS storm-total (`inundation_borough_spike`)
- **SFINCS Queens (Docker)** — this run (`inundation_sfincs`)

Rough compare (same Queens AOI, different physics / forcing):

| Engine | max depth (m) | wet >5 cm |
| --- | --- | --- |
| pysheds | ~0.15 | ~0.57 |
| SFINCS (uniform precip) | ~3.76 | ~0.49 |

Compare visually; do not treat either as calibrated DEP/NWS inundation. SFINCS is deeper because uniform ~10 mm/hr for 12 h with no infiltration/drainage calibration — research contrast only.
