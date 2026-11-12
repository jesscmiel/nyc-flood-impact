# Metro nested SFINCS — Advanced research hydro

**HAND stays primary.** SFINCS is an Advanced research hydro track only.  
**No SWMM** / no fake DEP pipe network. Open drainage sink = `drainage_capacity_proxy_v1`.  
No Enterprise / HENS. Research only — NOT official NWS / NOT decision-grade.

## What shipped

| Layer | Domain | Grid | Role |
| --- | --- | --- | --- |
| Metro coarse | `EXTENTS["metro"]` | ~100 m | Continuous Advanced hydro |
| Queens nest | `EXTENTS["south_queens"]` | ~50 m | Fine nest over South Queens / Jamaica Bay |
| Composite | metro grid + nest paste | — | Product Advanced toggle |

Shared forcing: **spatial** MRMS Ida storm-total → mm/hr rate field (`setup_precip_forcing_from_grid`, `aggregate=False`) minus open drainage capacity proxy. Uniform domain-mean forcing is forbidden.

## Docker

```bash
sg docker -c 'docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'

# Metro coarse
sg docker -c 'docker run --rm -v /home/jesscmiel/projects/nyc-flood-impact/outputs/sfincs_metro_ida:/data deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'

# Queens nest
sg docker -c 'docker run --rm -v /home/jesscmiel/projects/nyc-flood-impact/outputs/sfincs_queens_ida:/data deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'
```

One-shot:

```bash
.venv/bin/python scripts/build_and_run_sfincs_metro_nested.py
# reuse existing Queens nest NetCDF if fresh rebuild not needed:
.venv/bin/python scripts/build_and_run_sfincs_metro_nested.py --reuse-nest
```

## Artifacts

| Artifact | Path |
| --- | --- |
| Metro depth TIF | `data/processed/inundation/depth_sfincs_metro_ida_m.tif` |
| Nest depth TIF | `data/processed/inundation/depth_sfincs_queens_ida_m.tif` |
| Composite TIF | `data/processed/inundation/depth_sfincs_metro_nested_ida_m.tif` |
| Composite PNG | `figures/product_assets/depth_sfincs_metro_nested_ida_m.png` |
| Meta | `figures/product_assets/depth_sfincs_metro_nested_ida_meta.json` |
| Docker cmds | `outputs/sfincs_metro_nested_docker_commands.txt` |

## Run stats (this machine)

| Metric | Metro coarse | Queens nest | Composite |
| --- | ---: | ---: | ---: |
| max depth (m) | 5.526747703552246 | 3.092606544494629 | 5.526747703552246 |
| wet fraction (>5 mm) | 0.9769975708502024 | 0.9785201720685591 | 0.9790218623481781 |

Precip (shared sink): mean rate ≈ **7.903560638427734** mm/hr · max ≈ **18.573183059692383** · drain points n≈**154786** · sink applied=True.

## Product wiring

- Primary depth toggle = metro HAND × MRMS after drainage proxy (unchanged).
- Advanced · research hydro → **Metro nested SFINCS** (`lySfincsNested`) + optional Queens-nest-only (`lySfincs`).
- Manifest keys: `inundation_sfincs_nested`, `advanced_research_hydro`, `depth_engines.alternate`.

## Honesty

- Magnitudes are **not** peer-comparable to cm-scale HAND screening.
- Drainage sink ≠ DEP sewer performance ≠ SWMM.
- Nested composite pastes the Queens fine nest onto the metro coarse field for visualization — not a two-way coupled nest exchange.
