# SFINCS Docker run — South Queens / Ida

**No Enterprise / HENS. Research only — NOT official NWS.**

## Exact commands used

```bash
# Session needs docker group (use sg if freshly added to group):
sg docker -c 'docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'

sg docker -c 'docker run --rm -v /home/jesscmiel/projects/nyc-flood-impact/outputs/sfincs_queens_ida:/data deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'
```

Logged copy: `outputs/sfincs_queens_docker_commands.txt`

## Model

- Built with HydroMT-SFINCS `1.2.2` into `outputs/sfincs_queens_ida/`
- DEM: `/home/jesscmiel/projects/nyc-flood-impact/data/raw/terrain/dem_usgs_metro.tif` clipped via HydroMT region (South Queens bbox)
- Forcing: **spatial** MRMS precip grid (`setup_precip_forcing_from_grid`, aggregate=False) — not domain-mean
- Precip NetCDF: `/home/jesscmiel/projects/nyc-flood-impact/outputs/sfincs_queens_ida/forcing/mrms_spatial_precip_mmhr.nc`
- Rate stats (mm/hr): mean≈10.161332538607123, max≈16.935240427652996, CV≈0.29974688352111356
- Window: 2021-09-01 12Z → 2021-09-02 00Z

## Outputs

- Depth GeoTIFF: `data/processed/inundation/depth_sfincs_queens_ida_m.tif`
- PNG overlay: `figures/product_assets/depth_sfincs_queens_ida_m.png`
- Max depth ≈ **3.469573736190796** m (research)

## vs pysheds (primary)

- **Primary depth** = metro pysheds HAND/bathtub × spatial MRMS
- **SFINCS Queens** = alternate hydro track only (not peer toggle for magnitudes)

Compare visually; do not treat either as calibrated DEP/NWS inundation.

## Docker log summary

- pull rc: 0
- run rc: 0
- image digest pull: see `outputs/sfincs_queens_docker_log.json`
