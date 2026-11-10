# Flood risk product reset

**Honest status:** the current `nyc-flood-impact` UI is a **research case-study demo** (Hurricane Ida remnants over NYC). It is **not decision-grade**, not an official NWS product, and not ready to inform infrastructure or emergency response without major rebuild of hazard→inundation→exposure→risk metrics and validation.

**Hard constraints:** no Earth2Studio **Enterprise**, no **HENS** packages. Open Earth2Studio models (e.g. FCN / StormCast when dependencies install) and open hydro/data stacks only.

---

## What exists today (case study)

| Layer | Reality |
| --- | --- |
| Storm viz | MRMS QPE (~1 km) densified loop + open Earth2-class scenario tracks |
| “Susceptibility” | Heuristic weather × landscape × infra screening — not calibrated flood probability |
| Depth / alerts | pysheds HAND/bathtub depth + research thresholds — **not** NWS criteria |
| Exposure overlays | Roads / stations / 311 / FEMA / NWM / demo drainage — observational context |
| Validation | Exploratory overlays (311, gauges) — not certified skill |

**Gaps vs infrastructure-informing flood risk:** no return periods, no asset-level consequence model, no sewer/coastal coupling at DEP quality, no operational latency/SLA, no uncertainty communication suitable for responders.

---

## Target product (flood RISK)

Goal: **scenario and climatological flood risk for infrastructure and response planning** — screening that can eventually sit beside (not replace) agency products.

```
Hazard forcing  →  Inundation / hydrology  →  Exposure  →  Risk metrics  →  Validation
(MRMS/ERA5/GFS/   (pysheds → SFINCS or      (roads,      (depth×asset,    (311, gauges,
 open FCN/         LISFLOOD-FP; later         stations,    AAL/scenario,     NFHL, reports;
 StormCast)        drainage if open INP)      facilities)  RP placeholders)  honesty labels)
```

### Proposed open architecture

1. **Hazard**
   - Near-real-time / event: NOAA **MRMS** QPE/QPF, **GFS**/HRRR where available
   - Climatology / scenarios: **ERA5** (or similar) for historical analogs; design storms
   - AI (optional): **open** Earth2Studio prognostic (FCN family) / StormCast **only if** deps (`natten`, CUDA) install cleanly — labeled as scenario, never “radar”

2. **Inundation**
   - MVP: **pysheds** HAND + bathtub (already runnable)
   - Next: **SFINCS** or **LISFLOOD-FP** for pluvial/coastal compound where data exist
   - Sewer: **PySWMM** only with a real open/authorized network — do not fake DEP

3. **Exposure**
   - Citywide roads (OSM majors), transit, critical facilities, building footprints / census proxies
   - Keep FEMA NFHL / AHPS / NWM as **context**, not as the risk engine

4. **Risk metrics**
   - Event/scenario: max depth, wet fraction, assets intersected, disruption scores
   - Climatological MVP: placeholder **return-period** tables from historical MRMS/ERA5 analogs (clearly unlabeled as unofficial)
   - Later: AAL-style aggregates once hazard catalog exists

5. **Validation & honesty**
   - Hit rates vs 311 / gauges / high-water marks where available
   - Persistent UI: *research prototype — not decision-grade — not NWS*

---

## Prioritized MVP rebuild steps

1. **Stabilize product shell** — GeoJSON layers always load over HTTP (`scripts/serve_product.py`); no `err` counts; citywide exposure visible. ✅
2. **Reframe UI/docs as flood RISK** — Ida = case study fixture; remove Enterprise/HENS implications. ✅
3. **Package scaffold** — `flood_risk/{hazard,inundation,exposure,risk,validate}` (started). ✅
4. **Hazard catalog v0** — MRMS event packs + ERA5/GFS hooks; optional open FCN if installable. ✅ hooks in `hazard_catalog.json` (MRMS+Earth2 available; ERA5/GFS hook-only).
5. **Inundation v1** — keep pysheds; spike SFINCS or LISFLOOD-FP on one borough DEM. ✅ spike attempted — **binaries blocked**; pysheds borough v2 shipped (see `docs/inundation-engine-spike.md`).
6. **Exposure v1** — citywide roads/stations/facilities GeoPackage + intersect API. ✅ demo metro facilities + citywide roads/stations intersects
7. **Risk metrics v0** — depth×asset tables + scenario cards; RP placeholders with caveats. ✅ **citywide primary** + South Queens nested; UI scenario switcher
8. **Validation dashboard** — 311/gauge overlays with quantitative scores + confidence language.
9. **Only then** consider multi-city templates (same architecture, new fixtures).

---

## Non-goals (near term)

- Official watch/warning issuance
- Enterprise Earth2 / HENS ensembles
- Claiming calibrated DEP sewer response
- Replacing FEMA NFHL or agency flood maps

---

## Case study retention

Keep Ida NYC assets under `figures/product_assets/` as the first **fixture** for the risk shell. New cities/events should plug into the same `flood_risk` interfaces rather than forking the HTML.

Repo: `jesscmiel/nyc-flood-impact` · scaffold: `flood_risk/` · serve: `python scripts/serve_product.py`
