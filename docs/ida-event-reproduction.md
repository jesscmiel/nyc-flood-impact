# Ida event reproduction — FloodNet posts (first-step)

**Repo:** `jesscmiel/nyc-flood-impact` · **Branch:** `cursor/ida-floodnet-reproduction-7688`  
**Goal:** reproduce Ida **peak depths at FloodNet posts** (order-of-magnitude), not citywide HAND perfection.  
**Demo:** [product_map.html](../figures/product_map.html) · Skill card: `figures/product_assets/ida_floodnet_reproduction.json`

---

## Headline

| Compare | Peak RMSE | Bias (model−obs) | OOM ok |
| --- | ---: | ---: | ---: |
| **Primary metro HAND** (unchanged) | **0.53 m** | **−0.40 m** | **0 / 5** (all dry at post) |
| 10 m HAND nest | 0.50 m | −0.38 m | 1 wet @ Carroll only |
| SFINCS Queens @ Queens posts (n=2) | **0.024 m** | **−0.007 m** | **2 / 2** (already OOM) |
| **Hotspot hydro (this work)** | **0.21 m** | **~0 m** | **5 / 5** |

**Leave-one-out RMSE:** **0.32 m** (honesty check — fit is in-sample on n=5).

**One-line honesty:** Primary product depth stays cm-scale HAND screening. A **separate**, transparent scale+bias on local excess-precip ponding brings Ida peaks at the five 2021 FloodNet posts into the same order of magnitude as sensors. Residual error remains (esp. Hoyt overestimate / Carroll underestimate). **Not** citywide depth · **not** DEP/SWMM · **not** decision-grade.

---

## Why HAND fails at the posts

Stream HAND at Brooklyn posts is metres above street rain (e.g. Carroll HAND field ~7 m), so `depth = rain − HAND` is **dry**. Sensors measure local street ponding off the HAND wet channel. Rescaling HAND citywide would be fake; ignoring HAND at the post and using local excess precip is the transparent alternative.

---

## Method (transparent hotspot hydro)

1. Sample metro `excess_precip_mm` (MRMS after `drainage_capacity_proxy_v1`) at each FloodNet Ida event.  
2. Predictor: `x = runoff_coeff(0.70) × excess_mm / 1000` (same runoff as HAND bathtub; **no** stream HAND).  
3. Fit OLS: `depth_m = max(0, scale × x + bias_m)` on the five Ida peaks.  
4. Report in-sample RMSE/bias, leave-one-out, and per-sensor residual table.  
5. Also sample primary HAND, 10 m nest, and SFINCS Queens for peer context — **do not** blend into primary depth.

**Fitted coeffs (this run):** `scale ≈ 8.81`, `bias_m ≈ −0.140 m`.

Scripts: `flood_risk/validate/ida_hotspot.py`, `scripts/calibrate_ida_floodnet_hotspot.py`.

---

## Residual table (Ida FloodNet peaks)

| Sensor | Borough | Obs (m) | HAND | Nest 10 m | SFINCS | Hotspot cal | Residual |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BK-carroll-st-4th-av | Brooklyn | 0.90 | 0 | 0.085 | ~0.05 | ~0.61 | **−0.29** |
| BK-9th-st-smith-st | Brooklyn | 0.71 | 0 | 0 | ~0.01 | ~0.63 | **−0.08** |
| BK-hoyt-st-5th-st | Brooklyn | 0.26 | 0 | 0 | ~0.01 | ~0.63 | **+0.36** |
| Q-russell-st-2 | Queens | 0.07 | 0 | 0 | ~0.04 | ~0.065 | **−0.008** |
| Q-russell-st-1 | Queens | 0.04 | 0 | 0 | ~0.05 | ~0.053 | **+0.015** |

Queens: raw SFINCS already OOM without calib; hotspot matches closely. Brooklyn: SFINCS domain samples are near-dry; hotspot recovers ankle–knee scale but **over-smooths** Hoyt vs Carroll (same excess precip neighborhood → same cal depth).

---

## Demo honesty (talk track)

- Desk / map **primary depth** = metro HAND — still say “cm-scale screening.”  
- Desk **Ida FloodNet peaks** panel = **Ida post reproduction** (default-on map markers + residual list), not a new citywide hazard.  
- Quote hotspot RMSE **0.21 m** and LOO **0.32 m**; never 311 hit≈1.  
- Do not claim the scale/bias transfers to other storms without a holdout event.

---

## Product wiring

| Artifact | Path |
| --- | --- |
| Skill card | `outputs/ida_floodnet_reproduction.json` · `figures/product_assets/ida_floodnet_reproduction.json` |
| Station overlay | `figures/product_assets/floodnet_ida_hotspot_stations.geojson` |
| Manifest | `ida_event_reproduction` · `validation_dashboard.ida_reproduction` |
| Map | Decision Desk core panel **Ida FloodNet peaks** (default on) — residual list + map posts; Advanced keeps limitations-only note |

**Accept:** peaks OOM at FloodNet posts; residual documented; primary HAND unchanged; demo banner still research-only.
