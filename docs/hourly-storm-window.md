# Hourly Ida storm window · 0–36h native MRMS

**Repo:** `jesscmiel/nyc-flood-impact` · **Branch:** `cursor/hourly-storm-window-896e`  
**Demo:** [product_map.html](./product_map.html) · defaults stay **assets-first · Advanced closed · MRMS locked · susceptibility off**

---

## What changed

| Before (radar-style slice) | After (this slice) |
| --- | --- |
| Loop **+6…+24h** (19 frames) | Loop **+0…+36h** (**37** native hourly frames) |
| Native MRMS only at 6/12/18/24; in-between = temporal blends | **Native MultiSensor QPE 01H** every hour on metro soft-edge radar |
| Depth cum at 6/12/18/24 only; +18≈+24 (no recession) | Depth cum every **3h** (13 frames); **buildup → peak → recession** |
| Opens mid-event | Opens at init (**build-up** visible); closes after rain (**drainage** visible) |

---

## Actual Ida MRMS frame times

| | |
| --- | --- |
| **Init (reference)** | `2021-09-01T12:00` UTC |
| **Loop leads** | **+0h → +36h** (37 frames; native 1h MultiSensor QPE) |
| **Valid times** | `2021-09-01T12:00` → `2021-09-03T00:00` UTC |
| **Peak 1h precip (metro)** | ~+13…+14h (`2021-09-02T01:00`–`02:00`), max ≈ 80–84 mm/h |
| **Depth cum leads** | 0/3/6/…/36h (nearest-neighbor onto the 1h precip clock) |
| **Depth wetness** | dry through ~+9h · wet by +12 · **peak ~+18h** · **recedes through +36h** |

Precip motion is **native hourly MRMS**, not blend-only. Depth recession is a **screening story**: after +18h, effective drainage hours grow while cum precip plateaus so HAND excess can fall — not a calibrated hydrograph.

---

## Depth timeline (metro HAND × drainage proxy)

| Lead | Phase | max depth (m) | wet fraction |
| --- | ---: | ---: | ---: |
| +0…+9h | buildup | ~0 | 0 |
| +12h | buildup | ~0.06 | ~0.04 |
| +15h | buildup | ~0.15 | ~0.08 |
| **+18h** | **peak** | **~0.15** | **~0.088** |
| +24h | recession | ~0.14 | ~0.084 |
| +30h | recession | ~0.13 | ~0.079 |
| +36h | recession | ~0.12 | ~0.069 |

---

## How to regenerate

```bash
cd /home/jesscmiel/projects/nyc-flood-impact
# needs cfgrib + eccodes in the venv (pip install cfgrib eccodes)
.venv/bin/python scripts/fetch_ida_mrms_hourly_metro.py   # 0–36h → mrms_qpe_metro (local ~1 GB hourly/cum TIFs)
.venv/bin/python scripts/build_metro_inundation.py         # cum-depth 3h steps + recession drainage hours
.venv/bin/python scripts/rebuild_metro_radar_viz.py        # soft-edge PNGs + manifests
.venv/bin/python scripts/wire_metro_product_assets.py      # Decision Desk + product_map.html
.venv/bin/python scripts/serve_product.py
```

Hourly/cum metro GeoTIFFs are **gitignored** (regenerable). Product PNGs + manifests under `figures/product_assets/` are committed.

---

## Honesty

Research Ida replay only — **NOT NWS / NOT decision-grade / NOT NEXRAD tiles**. Soft-edge metro MRMS is MultiSensor QPE (~1 km), not reflectivity. HAND puddles remain heuristic cm-scale screening.
