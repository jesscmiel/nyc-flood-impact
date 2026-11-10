# STRATA pipeline investigation (Earth2 → STRATA → SFINCS → assets)

**Host:** `earth2-nyc` (Alienware / RTX 4090, ~24 GB). Repos: `nyc-flood-impact` + `earth2studio`.  
**Scope:** Feasibility of `large-scale Earth2 state → STRATA → high-res precip → SFINCS → inundation → assets`.  
**No Enterprise / HENS.** Research only — not official NWS.

**Verdict:** The pipeline as written is **not plug-and-play**. STRATA is a **SCREAM km-scale emulator**, not a downscaler of open FCN/SFNO. Downstream SFINCS + exposure intersects **are ready**. The hard gaps are **ICs, dates (Ida), and coupling**.

---

## 1. Can open FCN / SFNO provide ICs / state for STRATA?

**Short answer: no — not with the public checkpoint and tooling.**

| Piece | FCN / SFNO (Earth2Studio open) | STRATA v1 |
| --- | --- | --- |
| Role | Global ~0.25°, ~6 h autoregressive weather | Global ~4.9 km, 10 min SCREAM emulator |
| Grid | Lat/lon (ERA5/GFS-like) | Cubed-sphere `ne1024pg2` (6×2048×2048) |
| State | Standard Earth2 lexicon (z, t, u, v, q, …) | SCREAM: `PotentialTemperature`, `U`, `V`, `z_mid`, `omega`, `qv`, `T_2m` + forcings |
| ICs for released forecast | GFS / ERA5 via Earth2Studio data sources | **Only** SCREAM Zarr (`STRATA-SCREAM-sdecadal`), streamed or local |

Public forecast path (`scripts/ace/run_screamcast_nudged.py`) loads the IC from `SCREAM_MAIN_ZARR_PATH`, not from an SFNO/FCN package.

**ACE → SCREAM docs do not reverse this.** `docs/ace2scream_finetuning.md` trains an SFNO-scale **residual correction** used to *nudge* STRATA rollouts that **still start from SCREAM ICs**. That is large-scale coupling research, not “FCN output = STRATA IC.”

HF model card lists “coupling AI emulators of different resolutions (e.g. large-scale nudging / downscaling experiments)” as a **use-case aspiration**, not a shipped Earth2Studio adapter.

**Implication for the asked pipeline:** treat “Earth2 large-scale state → STRATA” as a **research bridge** (regrid + physics remap + optional nudge/finetune), not an install step.

---

## 2. STRATA install, checkpoints, VRAM, Ida-relevant data

### Install (NVlabs/STRATA + PhysicsNeMo)

- **Architecture:** `physicsnemo.experimental.models.strata` (in NVIDIA PhysicsNeMo).
- **SCREAM glue / rollout:** [NVlabs/STRATA](https://github.com/NVlabs/STRATA) package name `screamcast`.
- **Recommended env:** NGC `nvcr.io/nvidia/pytorch:26.09-py3` + repo `docker/Dockerfile` (builds NATTEN for Ada/Hopper). Plain `pip install -e . -f https://whl.natten.org` is possible but less tested.
- **Weights:** [huggingface.co/nvidia/strata](https://huggingface.co/nvidia/strata) — `checkpoints/strata_v1.pth` (~1.27 GB, OpenMDW 1.1) + static `phis.npy` / `sgh30.npy` / `landfrac.npy` (~96 MB each).
- **Aux:** `AUX_DATA_ROOT` with checkpoint + static fields + SCRIP/latlon generated via `data_prep/scrip_generation/generate_all.sh` (~20 min on a 64-core node; multi-GB intermediates).
- **ICs for forecast:** `SCREAM_MAIN_ZARR_PATH=hf://datasets/nvidia/STRATA-SCREAM-sdecadal` (full store **~36.8 TB** if downloaded; HTTP stream OK for IC-only forecast).

### Smoke check on `earth2-nyc` (this machine)

| Check | Result |
| --- | --- |
| GPU | RTX 4090, ~24.4 GB free at idle |
| `earth2studio` venv | 0.21.0a0; torch 2.13+cu130; **physicsnemo 2.3.0a0** |
| `from physicsnemo.experimental.models.strata import Strata` | **OK** (experimental warning) |
| `screamcast` / `earth2grid` | **Not installed** in current venv |
| Download `strata_v1.pth` | **OK** (~48 s → `/tmp/strata_smoke/checkpoints/strata_v1.pth`) |
| `torch.load` checkpoint | **OK** — `network` (331.7 M params), norms, `train_config`, `release.name=strata_v1` |
| `Strata.from_checkpoint` (PhysicsNeMo Module API) | **Fails** — expects Module `args.json` layout; release uses screamcast training dict |
| `ScreamcastModel.from_checkpoint` | Needs full STRATA deps (`earth2grid`, `lightning`, NATTEN, …) — **not a 1-minute smoke** |

Conclusion: **architecture + checkpoint bytes are reachable on the 4090 today**; a real forward pass needs the STRATA Docker / full `screamcast` stack.

### VRAM: NYC tile vs global

| Mode | Guidance from public docs / paper | Fit on 1×4090 (~24 GB)? |
| --- | --- | --- |
| **Global** recommended forecast | `torchrun` **4×H100 80 GB**, `--tile-size 128`, `--halo-width 16`, `--inference-batch-size 1`; ~1.5–2.5 min per 10 min step | **Unlikely** as documented |
| **Per-tile** | Single GPU advances any tile; paper benches **64×64** tile on **1×H100 80 GB** (BF16, batch 1); production FT uses **128×128** (~576 km) | **Plausible** for 1–few tiles with BF16/eager; must be measured |
| **NYC AOI** | A few ~128 px tiles cover metro-scale domain **if** IC/state exists for those columns | Conceptually yes; public scripts still assemble **global** cube faces |

**Do not assume** “NYC-only” avoids needing a valid SCREAM global (or at least halo-consistent) state at t₀.

### Ida-relevant dates / data

| Dataset | Calendar content | Ida (2021-09-01) useful? |
| --- | --- | --- |
| `STRATA-SCREAM-sdecadal` | Labeled **2020-10-01 … 2020-10-15** in code; atmosphere from **1994** F20TR with Oct 2020 SSTs | **No** — weather ≠ Ida; docs say evaluate vs SCREAM, **not** observations |
| `sdy1` / `sdy2` | Aug 2016 / Jan 2020 DYAMOND-style segments | **No** Ida |
| Training window | 17 SCREAM days (Oct/Aug/Jan subsets) | No Sept 2021 |

**Ida replay through STRATA is blocked** without a custom SCREAM (or carefully remapped) IC for that event. Closest honest spike: run STRATA on a **held-out sdecadal IC**, extract NYC precip, drive SFINCS as a **methods demo** (not an Ida case study). Keep Ida precip via **MRMS / FCN+PrecipAFNO** paths already in `nyc-flood-impact`.

---

## 3. How STRATA precip would force SFINCS (Docker already works)

STRATA diagnoses each 10 min step:

- `precip_liq_surf_mass_flux`, `precip_ice_surf_mass_flux` (**m/s**, SCREAM units)
- Ice precip is **0** on the released checkpoint (known limitation)

**Conversion (research):**

```text
mm/hr ≈ precip_liq_surf_mass_flux * 1000 * 3600
storm_total_mm = sum(rate_mm_hr * dt_hr) over steps
```

**Wire into existing Queens SFINCS stack** (`scripts/build_and_run_sfincs_queens.py`, image `deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release`):

1. Regrid selected cube-face columns → WGS84 / UTM over South Queens (or citywide) bbox.
2. Write HydroMT precip forcing:
   - **MVP:** domain-mean rate → `setup_precip_forcing(magnitude=…)` (what Ida/MRMS spike does today).
   - **Better:** spatially varying precip field / timeseries HydroMT supports for SFINCS.
3. Same Docker mount:

```bash
sg docker -c 'docker pull deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'
sg docker -c 'docker run --rm -v "$PWD/outputs/sfincs_queens_ida:/data" deltares/sfincs-cpu:sfincs-v2.1.1-Dollerup-Release'
```

4. Export `hmax` → GeoTIFF (already implemented) → product map toggle vs pysheds.

Caveats: ~4.9 km STRATA precip is still **much coarser** than 50 m SFINCS grid; expect smooth forcing + research-only depths (same honesty labels as current SFINCS spike).

---

## 4. Asset intersect (existing exposure GPKG)

Already in tree:

- Builder / intersect: `flood_risk/exposure/geopackage.py` → `intersect_depth_gpkg`
- Product asset: `figures/product_assets/exposure_citywide.gpkg`

| Layer | Count | Geometry |
| --- | --- | --- |
| `roads` | 2200 | LineString |
| `stations` | 309 | Point |
| `facilities` | 26 | Point |

**Spike glue:** point `intersect_depth_gpkg(gpkg, depth_sfincs_*.tif, bands=…)` at the SFINCS depth GeoTIFF — same path as pysheds risk tables. No new exposure schema required for a v0 STRATA demo.

---

## 5. Blockers

1. **IC modality mismatch** — FCN/SFNO cannot initialize public STRATA.
2. **No Ida SCREAM IC** — public stores are Oct/Aug/Jan SCREAM segments, not 2021-09-01.
3. **Env gap** — NATTEN / DALI / `earth2grid` / NGC stack vs current `earth2studio` venv (architecture import works; rollout wrapper does not).
4. **VRAM** — documented global rollout is multi-H100; 4090 is a **tile/regional experiment**, not a drop-in global box.
5. **Data volume** — full sdecadal Zarr ~37 TB; IC streaming helps forecast but not offline training.
6. **License** — weights OpenMDW 1.1 (review before redistribution).
7. **SFINCS spatial precip** — current HydroMT path is uniform magnitude; spatial STRATA fields need a small forcing upgrade.
8. **Scientific honesty** — STRATA free-running bias grows with lead; ice precip broken; not calibrated inundation.

---

## 6. Minimal spike plan (no Enterprise/HENS)

**Goal:** Prove `STRATA precip → Docker SFINCS → GPKG intersect` on `earth2-nyc`, **without** claiming Ida or FCN ICs.

1. Build STRATA Docker image from NVlabs/STRATA; mount repo + `AUX_DATA_ROOT`.
2. `hf download nvidia/strata` (checkpoint already smoke-cached under `/tmp/strata_smoke` on this host).
3. Generate SCRIP/latlon aux; set `SCREAM_MAIN_ZARR_PATH=hf://datasets/nvidia/STRATA-SCREAM-sdecadal`.
4. Run **`--n-steps 2`** (docs’ quick check) or marimo single-tile notebook; prefer precip-only outputs.
5. Clip/regrid precip over NYC bbox → mm/hr series or storm total.
6. Rebuild Queens HydroMT model with that rate/field; run existing Docker SFINCS; export depth TIF.
7. `intersect_depth_gpkg` on `exposure_citywide.gpkg`; dump JSON next to current risk tables.
8. Document commands + “SCREAM IC / not Ida / not FCN-initialized” banners on the product map.

**Parallel Ida path (already mostly built):** GFS/ERA5 → FCN or SFNO → PrecipAFNO (and/or MRMS QPE) → SFINCS / pysheds → same GPKG. Optionally explore **StormCast** later for CONUS km-scale — different model, different domain (not STRATA).

**Out of scope for minimal spike:** training ACE→SCREAM residual, generating SCREAM ICs for Ida, full 24 h global STRATA on one 4090.

---

## 7. Effort (technical, not calendar)

| Slice | Invasiveness | Dependencies / risk |
| --- | --- | --- |
| A. STRATA Docker + 2-step smoke on 4090 | Ops / env | NGC image, NATTEN build, HF IC stream, VRAM tuning |
| B. NYC precip extract → uniform SFINCS → GPKG | Small code in `nyc-flood-impact` | Regrid correctness; reuse Docker SFINCS |
| C. Spatial SFINCS precip timeseries | Moderate HydroMT/SFINCS forcing | Still research depths |
| D. FCN/SFNO → SCREAM-like IC / nudge for STRATA | Large research | Variable remap, vertical coords, nudging stability; no public Ida IC |
| E. True Ida STRATA case study | Blocked pending SCREAM (or equivalent) IC | Data generation outside current open stores |

**Recommended sequence:** A → B (methods demo) while Ida stays on MRMS/FCN; only invest in D/E if there is a concrete SCREAM IC strategy.

---

## 8. References (primary)

- [NVlabs/STRATA README](https://github.com/NVlabs/STRATA)
- [nvidia/strata (HF)](https://huggingface.co/nvidia/strata)
- [arXiv:2606.31248](https://arxiv.org/abs/2606.31248)
- Repo: `docs/sfincs-docker-run.md`, `scripts/build_and_run_sfincs_queens.py`, `flood_risk/exposure/geopackage.py`
