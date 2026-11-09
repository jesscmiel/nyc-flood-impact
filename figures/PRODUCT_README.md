# Product map guide

Open [`product_map.html`](./product_map.html) via a static server:

```bash
cd figures && python3 -m http.server 8765 --bind 127.0.0.1
```

## Tracks shipped in this UI

1. **Precip credibility** — Always-visible coarse-grid notice; bilinear vs nearest display toggle; ensemble band control (enabled when multi-member NetCDF exists). StormCast/CorrDiff are documented hooks only — no fake downscaling.
2. **Pluvial screening** — Terrain + imperviousness index. Labeled as screening, not depth. SWMM still needs a calibrated NYC INP.
3. **Product UI** — Event picker (Ida + placeholder), extent selector (South Queens / citywide view), clock valid times, shareable `#` URL state, mobile stacking layout, sticky disclaimers.
4. **Ops** — `make live-ida` / `scripts/run_live_pipeline.py` rebuild path; exposure notes only.
5. **Validation** — Earth2 vs MRMS vs 311 snapshot panel from `outputs/validation_product.json`.

## What this is not

Not inundation depth, not NWS flood warnings, not emergency guidance, not a certified verification scorecard.
