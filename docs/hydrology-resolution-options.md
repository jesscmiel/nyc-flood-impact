# Hydrology & resolution options (honest assessment)

**App:** https://github.com/jesscmiel/nyc-flood-impact  
**Machine:** earth2-nyc · RTX 4090 (24 GB) · Earth2Studio as dependency only  

## Short answers

1. **Can we add “real hydrology” for a real flood susceptibility model?**  
   Yes for **relative flood susceptibility / pluvial screening** (terrain + built surface + optional rainfall exposure).  
   **No** (not yet) for **calibrated inundation depths or street-flood warnings** — that needs a calibrated NYC sewer/drainage model (SWMM INP + gages) we do not have.

2. **Is higher-resolution data available?**  
   **Yes**, already partly on disk and/or publicly fetchable — but native Earth2 FCN precip stays ~0.25°. Higher-res precip needs StormCast/CorrDiff (or stick with MRMS ~1 km as the observed reference).

---

## Susceptibility vs inundation (definitions)

| Term | Meaning | What we can claim |
| --- | --- | --- |
| **Terrain / pluvial screening** | Relative index: low/flat land + built/impervious → more street-flood *susceptibility* | Yes — exploratory product layers |
| **Event exposure screening** | Screening × storm rainfall intensity (MRMS or Earth2) | Yes — still not depth |
| **Flood susceptibility model** | Static or quasi-static ranking of locations | Partial — uncalibrated heuristic |
| **Inundation / flood depth** | Water depth / extent from hydrology or hydraulics | **No** without SWMM/HEC-RAS + calibration |
| **Flood warning** | Operational NWS-style alert | **Never** in this prototype |

---

## What we have today

| Layer | Status on this machine | Resolution | Honesty |
| --- | --- | --- | --- |
| Earth2 FCN + PrecipitationAFNO | Ran for Ida | ~0.25° native (~25 km) | Underestimates Ida vs MRMS |
| MRMS MultiSensor QPE | Cached for Ida leads | ~1 km | Observed precip reference |
| USGS 3DEP DEM | `data/raw/terrain/dem_usgs_1_3_arcsec.tif` | ~10 m (1/3″) | Real |
| Terrain screening | `terrain_screening_10m.tif` | ~10 m | Terrain-only index |
| Impervious GeoTIFF | `impervious_surface.tif` | Coarse **demo** (near-constant ~0.55) | **Rejected** by improved pluvial builder |
| Built-surface proxy | OSM highways → raster | ~30 m product grid | Road corridor proxy, not NLCD |
| Pluvial screening | Rebuilt: terrain + built proxy | ~30 m display / DEM-derived | Screening only |
| SWMM | Code scaffold in `swmm.py` | n/a | **Blocked** — no calibrated NYC INP |
| StormCast / CorrDiff | Importable in E2S venv | km-scale regional | Weights/conditioning not run here |

---

## Higher-res data that exists (public / on-machine)

### Precipitation
- **MRMS QPE (~1 km, hourly)** — already used; best observed precip for validation.
- **HRRR / RAP** — ~3 km; good IC/conditioning for StormCast paths.
- **StormCast / StormCastCONUS** (Earth2Studio) — generative convection-allowing regional precip; needs PhysicsNeMo weights + conditioning data source (often HRRR). Feasible on RTX 4090 for limited domains/leads; **not free** in setup time.
- **CorrDiff\*** diagnostics (e.g. `CorrDiff`, `CorrDiffEra5Hrrr`) — downscale global → regional; also weight/runtime dependent. Prefer real model output over bilinear “fake resolution.”

### Terrain / land cover / hydro
- **USGS 3DEP DEM** — already clipped for South Queens (~10 m).
- **NLCD percent impervious (~30 m)** — real product at MRLC; **not yet downloaded** (previous file was a demo placeholder). Next fetch target.
- **NYC Open Data** — catch basins, 311, buildings/planimetrics (building footprints → better impervious than roads alone).
- **NWM (National Water Model)** — streamflow / land-surface; useful for riverine context, weak for NYC street pluvial without urban routing.
- **FEMA NFHL** — regulatory flood hazard zones (static); good context overlay, not event inundation.
- **SWMM** — needs agency-calibrated NYC drainage INP + rain gage map; scaffold only until that exists.

---

## Feasibility on this GPU machine

| Path | Feasible? | Notes |
| --- | --- | --- |
| Better pluvial from DEM + OSM/NLCD | **Yes (done / next)** | DEM already local; OSM roads used; NLCD still to fetch |
| MRMS 1 km as “higher-res precip” vs Earth2 | **Yes (done)** | Observation, not a forecast downscaler |
| StormCastCONUS / CorrDiff for Ida | **Maybe** | RTX 4090 OK; needs weights download, HRRR conditioning, NYC domain check |
| Calibrated SWMM depths | **Blocked** | Missing INP — do not invent depths |
| Full citywide 1 m DEM + buildings raster | **Heavy** | Possible offline; larger I/O than current prototype |

---

## Recommended next implementable steps (priority)

1. **Done this pass:** Reject demo impervious; rebuild pluvial with USGS terrain screening + OSM road built-surface proxy; denser product grid; map layer for built proxy.  
2. **Next (small):** Fetch real **NLCD 30 m impervious** for the study bbox and swap it in for the road proxy (keep proxy as fallback).  
3. **Next (medium):** Optional **event exposure** layer = pluvial × normalized MRMS (or Earth2) — still labeled screening.  
4. **Next (medium/large):** Spike **StormCast** or **CorrDiffEra5Hrrr** on Ida with E2S venv; only ship if outputs are real model fields.  
5. **Blocked:** SWMM depth maps until a calibrated NYC INP is supplied.

---

## What we will not claim

- Street flood depths, basement water levels, or “will flood / won’t flood” decisions  
- That bilinear resampling or road density is physical downscaling  
- That susceptibility equals FEMA risk or NWS warnings  
