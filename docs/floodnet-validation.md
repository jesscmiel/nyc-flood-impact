# FloodNet validation — Ida vs primary metro HAND

**Repo:** `jesscmiel/nyc-flood-impact` · **Branch:** `cursor/floodnet-validation-5dcc`  
**Compare:** FloodNet street sensors × **primary** metro HAND depth (drainage-proxy excess)  
**Not:** SFINCS peer score · 311 hit-rate theater · decision-grade skill

Skill card: `outputs/floodnet_validation.json` · Stations: `figures/product_assets/floodnet_ida_stations.geojson`

---

## Headline (lead with this — never 311 hit≈1)

| Metric | Ida FloodNet pilot | Read |
| --- | ---: | --- |
| Sensors / events in window | **5 / 5** (Brooklyn + Queens) | Sparse 2021 network — pilot, not citywide grid |
| Obs peak mean / max | **0.40 / 0.90 m** | Street flooding up to ~36 in |
| Model peak at sensor mean / max | **0.00 / 0.00 m** | All 5 sensors land on dry HAND cells |
| Peak **bias** (model − obs) | **−0.40 m** | Systematic under-depth |
| Peak **RMSE** | **0.53 m** | Magnitude gap, not noise |
| Timing error | **undefined** (n=0) | Model dry/flat at sensors → no wet peak to time |
| Nearest-wet HAND ≤250 m (n=2) | bias **−0.37 m**, RMSE **0.43 m** | Even local wet cells stay cm-scale |

**One-line honesty:** FloodNet confirms primary HAND is **cm-scale screening** that misses Ida street peaks. Do **not** multiply HAND to chase metres.

---

## Data & scripts

| Source | Role | Status |
| --- | --- | --- |
| NYC Open Data `aq7i-eu5q` | Flooding events + depth time series | Used (5 Ida-window events) |
| NYC Open Data `kb2e-tjy3` | Sensor lat/lon | Used |
| Zenodo sep-2021 minute CSV | Optional high-rate timeseries | Unavailable here (403) |

```bash
.venv/bin/python scripts/fetch_floodnet_ida.py
.venv/bin/python scripts/run_floodnet_validation.py
.venv/bin/python scripts/science_audit_recompute.py
```

Module: `flood_risk/validate/floodnet.py` · Window: `2021-09-01T12Z` → `2021-09-03T00Z` (product clock).

---

## Method (short)

Sample storm-total + cum-lead HAND at each sensor (`nodata` dry → 0 m). Report peak RMSE/bias, series bias, and timing only when the HAND timeline is wet (≥5 mm). Optional nearest-wet ≤250 m documents cell misalignment without closing the magnitude gap.

Primary path unchanged — no ad-hoc HAND rescale.

---

## Product wiring

- Manifest: `validation_floodnet`, `validation_dashboard.lead_metric=floodnet_peak_rmse_bias_timing`, `bury_311_hit_rate=true`
- Map panel leads with FloodNet RMSE/bias when the skill card is present
- Science audit includes `floodnet_validation` + `validation_lead` (311 exploratory only)
