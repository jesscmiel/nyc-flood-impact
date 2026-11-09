# Hydrology & resolution options (living)

**App:** https://github.com/jesscmiel/nyc-flood-impact  
**Machine:** earth2-nyc · RTX 4090 (24 GB) · Earth2Studio dependency only  

## Short answers

1. **Real hydrology / susceptibility:** Relative **pluvial screening** is in place (USGS ~10 m terrain + **NLCD 2021 ~30 m impervious**). Calibrated **inundation depths** remain blocked without a NYC SWMM INP.
2. **Higher-res precip:** MRMS QPE ~1 km is the observed reference. StormCast / CorrDiff **attempted on this GPU** but **blocked on `natten`** (see below). No fake downscaling shipped.

---

## Status of the three approved next steps

| Step | Status | Notes |
| --- | --- | --- |
| 1. Real NLCD ~30 m impervious + rebuild pluvial | **Done** | Fetched via MRLC WCS; demo constant raster replaced; pluvial formula `0.55*terrain + 0.45*NLCD`; map rebuilt |
| 2. StormCast and/or CorrDiff for Ida NYC | **Blocked** | RTX 4090 present; StormCastCONUS **weights load**; both StormCast forward and CorrDiffEra5Hrrr require **`natten`**. `uv sync --extra corrdiff-era5-hrrr` failed building natten 0.21.7 (cmake, CUDA arch 89). Report: `outputs/stormcast_corrdiff_attempt.json` |
| 3. FEMA NFHL and/or NWM context overlays | **Done (MVP)** | FEMA SFHA polygons + NWM high-flow reaches + AHPS river gauges on product map, labeled **static/context — not event inundation** |

---

## Susceptibility vs inundation

| Term | Claimable? |
| --- | --- |
| Pluvial / terrain screening | Yes — relative index |
| NLCD impervious | Yes — land cover input |
| FEMA NFHL | Yes — static regulatory context |
| NWM / AHPS | Yes — channel / gauge context |
| StormCast / CorrDiff precip | Not yet — blocked on natten |
| SWMM street depths | No — missing calibrated NYC INP |
| Flood warnings | Never in this prototype |

---

## Exact StormCast / CorrDiff blockers

```text
CorrDiffEra5Hrrr.load_model → OptionalDependencyError
  needs earth2studio extra `corrdiff-era5-hrrr`
  root cause: ImportError: No module named 'natten'

StormCastCONUS.load_model → succeeds on RTX 4090
StormCastCONUS forward → ImportError: Missing optional dependency: natten
  hint: pip install "nvidia-physicsnemo[cu12,natten-cu12]"

uv sync --extra corrdiff-era5-hrrr → FAILED
  natten 0.21.7 source build: cmake returned non-zero
  (-DNATTEN_CUDA_ARCH_LIST=89-real)
```

**Policy:** leave hooks + JSON report; do **not** bilinear-fake higher-res precip.

Retry when a prebuilt `natten` wheel matches this torch / CUDA 12 / py3.13 / sm_89 stack.

---

## Data now on disk / in map

- `data/raw/landcover/nlcd_2021_impervious_south_queens.tif` (+ refreshed `impervious_surface.tif` as 0–1)
- `data/raw/context/fema_nfhl_south_queens.geojson` (full pull); map uses SFHA subset
- `figures/product_assets/nwm_high_flow.geojson`, `nwm_ahps_gauges.geojson`
- Scripts: `fetch_nlcd_impervious.py`, `fetch_context_overlays.py`, `try_stormcast_corrdiff.py`

## Screenshots

- `media/product-ui.png`
- `media/hydrology-context.png`
- `media/validation-panel.png`
