# NYC Flood Impact

Standalone prototype for an Earth-2–powered NYC flood-impact map (Hurricane Ida remnants, 2021-09-01).

**Earth2Studio is a dependency only** — not an upstream NVIDIA contribution.

## Quick open

```bash
cd /home/jesscmiel/projects/nyc-flood-impact
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
python scripts/build_product_map.py
cd figures && python3 -m http.server 8765 --bind 127.0.0.1
# http://127.0.0.1:8765/product_map.html
```

Worker tip: point Cursor `--worker-dir` at `/home/jesscmiel/projects/nyc-flood-impact`.

## Product upgrades (5 tracks)

| Track | Status | What’s in the repo |
| --- | --- | --- |
| **1 Precip credibility** | Partial | Coarse-grid UI notice; bilinear vs nearest display; 2-member ensemble spread layer wired. StormCast/CorrDiff documented as next hooks — **no fake downscaling** / no StormCast run this pass. |
| **2 Real hydrology** | Partial | Pluvial screening = USGS ~10&nbsp;m terrain + **NLCD 2021 ~30&nbsp;m impervious**. FEMA SFHA + NWM/AHPS context overlays (static/context labels). StormCast/CorrDiff **blocked on `natten`**. SWMM still needs NYC INP. See `docs/hydrology-resolution-options.md`. |
| **3 Product UI** | Done (MVP) | Event picker (Ida + placeholder), South Queens / citywide extent, clock valid times, `#` URL state, mobile stack layout, sticky disclaimers → `figures/product_map.html`. |
| **4 Ops path** | Done (MVP) | `scripts/run_live_pipeline.py` + `make live-ida` / `make live`. Freshness notes; exposure scores only — never flood warnings. Auth/hosting deferred. |
| **5 Validation** | Done (MVP) | `scripts/run_validation_report.py` → `outputs/validation_product.json` + map panel (Earth2 vs MRMS vs 311). |

See also `figures/PRODUCT_README.md` and Project store `docs/product-upgrades-plan.md`.

## Earth2Studio install

```bash
# Sibling editable checkout (recommended on this machine)
pip install -e /home/jesscmiel/projects/earth2studio

# Forecast (GPU env)
python scripts/run_earth2_forecast.py \
  --init-time 2021-09-01T12:00:00 --steps 4 --members 1 \
  --output data/forecasts/earth2_precip_ida.nc
```

Multi-member uncertainty (Track 1):

```bash
python scripts/run_earth2_forecast.py --init-time 2021-09-01T12:00:00 --steps 4 --members 4 \
  --output data/forecasts/earth2_precip_ida_ens.nc
```

### Downscaling hooks (not run by default)

```bash
# Probe imports in the Earth2Studio venv (weights still required to actually run):
/home/jesscmiel/projects/earth2studio/.venv/bin/python scripts/document_higher_res_precip.py
```

- `earth2studio.models.px.StormCast` / `StormCastCONUS` — higher-res regional path when weights + conditioning (often HRRR) allow.
- `earth2studio.models.dx.CorrDiff*` — diagnostic downscaling after a global prognostic.
- Observed higher-res precip already in-repo: **MRMS QPE ~1 km**.
- Policy: prefer real model outputs over interpolating fake resolution.

## Makefile

```bash
make map          # build product_map.html
make validation   # refresh validation JSON
make live-ida     # rebuild from existing Ida clipped forecast + MRMS QA assets
make live INIT=2021-09-01T12:00:00   # GPU forecast via E2S_PYTHON then map
```

## License

Apache-2.0 for application code in this repo. Earth2Studio, OSM, NYC Open Data, and NOAA MRMS retain their own terms.
