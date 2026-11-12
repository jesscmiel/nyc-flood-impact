# Sewer / drainage capacity proxy (research)

**Repo:** `jesscmiel/nyc-flood-impact` · **Branch:** `cursor/sewer-drainage-calibration-8241`  
**Question:** can we calibrate for sewer performance?  
**Answer:** yes — as an **open, literature-anchored capacity proxy** that reduces effective precip before HAND (and optionally SFINCS rates). **No** proprietary DEP sewer model, **no** fake pipe network, **no** SWMM INP.

Demo: [product_map.html](product_map.html) · Assets: [product_assets/](product_assets/) · Meta: [product_assets/drainage_capacity_meta.json](product_assets/drainage_capacity_meta.json)

---

## What shipped

| Piece | Role |
| --- | --- |
| `flood_risk/inundation/drainage_capacity.py` | Proxy engine `drainage_capacity_proxy_v1` |
| `scripts/build_drainage_capacity_proxy.py` | Builds capacity / sink / excess rasters + loose calibration JSON |
| `scripts/build_metro_inundation.py` | Primary HAND depth uses **excess precip after sink** |
| `scripts/build_and_run_sfincs_queens.py` | Optional excess **rate** field for next SFINCS rebuild |
| Undrained baseline | `depth_metro_mrms_undrained_ida_storm_total_m.tif` (diagnostic only) |

**Primary depth remains labeled** metro pysheds HAND/bathtub × spatial MRMS, now with forcing kind  
`spatial_mrms_qpe_ida_minus_drainage_capacity_proxy`. SFINCS Queens stays **alternate hydro track**.

---

## Method (honest)

```
capacity_mm_hr = (CAP_BASE + (CAP_MAX − CAP_BASE)·drain_norm) · (1 − α·impervious)
intensity      = precip_mm / event_duration_hr          # 12 h Ida window
efficiency     = 1 / (1 + k · max(0, intensity/capacity − 1)²)   # surcharge collapse
sink_mm        = min(precip, capacity · effective_drainage_hours · efficiency)
excess_mm      = precip − sink
depth          = HAND/bathtub(excess_mm)               # primary product
```

**Knobs (literature order-of-magnitude, not DEP-certified):**

| Knob | Value | Rationale |
| --- | --- | --- |
| `CAP_BASE_MM_HR` | 10 | Sustained multi-hour capacity under load (low inlet density) |
| `CAP_MAX_MM_HR` | 22 | ~0.9 in/hr when open drain points support higher capacity |
| `ALPHA_IMPERVIOUS` | 0.35 | High pavement → less residual infiltration assist |
| `SURCHARGE_K` | 0.85 | Efficiency drops when intensity ≫ capacity (Ida overload) |
| `EVENT_DURATION_HR` | 12 | Mean intensity + SFINCS window |
| `EFFECTIVE_DRAINAGE_HOURS` | **3** | Peak flash hours of near-design removal — **not** capacity×12 h (that over-drains Ida totals) |

**Open inputs only**

- NLCD 2021 impervious (warped to metro grid)
- Metro open catch-basin inventory when present (`scripts/fetch_osm_drains_metro.py` → NYC Open Data CSV + OSM); South Queens OSM (**84**) is the thin fallback
- Coverage fraction of land cells with inlet credit is recorded in `drainage_capacity_meta.json` (transparent NLCD-base elsewhere)
- Synthetic demo `drainage_nodes` / SODA error payloads **excluded** (no fake network credit)

---

## Loose calibration vs Ida / 311

| Check | Result | Limit |
| --- | --- | --- |
| 311 hit ≥3 cm (drained primary) | **~0.98** | Spatial concentration only — **not** magnitude skill / ROC |
| Random-land hit ≥3 cm | **~0.01** | Useful baseline; 311 ≫ random |
| Fraction precip removed (rain>0 cells) | **~0.18** | Screening sink, not measured sewer volume |
| Primary max depth | **~0.13 m** | Still **shallow vs Ida street narratives** (ankle–knee+ pockets) |
| Undrained max (diagnostic) | **~0.14 m** | Proxy is a modest volume correction on HAND, not a depth fix |
| FloodNet citywide grid | **Absent** | Narrative bands only (nuisance / ankle / knee / extreme) |
| DEP catch-basin citywide | **Unavailable** | Prior SODA pull is an error payload |

**Cannot claim:** calibrated DEP performance, SWMM street depths, official NWS guidance, or decision-grade sewer ops.

---

## How to re-run

```bash
.venv/bin/python scripts/build_metro_inundation.py
.venv/bin/python scripts/build_drainage_capacity_proxy.py
.venv/bin/python scripts/science_audit_recompute.py
.venv/bin/python scripts/wire_metro_product_assets.py
# optional next SFINCS rebuild picks up excess-rate forcing:
# .venv/bin/python scripts/build_and_run_sfincs_queens.py
```

Outputs: `data/processed/drainage_capacity/`, `figures/product_assets/drainage_capacity_*.{tif,png,json}`, `outputs/science_audit_recompute.json`, Decision Desk JSON/HTML.

---

## Science note

This closes the audit item “infiltration + simple drainage capacity proxy (mm/hr sink)” without inventing a DEP network. It **does not** reconcile pysheds cm-scale depths with SFINCS meter-scale Queens depths; those remain non-peer. Magnitude skill vs Ida narratives remains an open gap (hi-res DEM, routing, real inlet inventory).
