# Citywide flood risk + hazard catalog

**Primary extent:** NYC metro / citywide (not South Queens–only).

## Depth × asset risk

- Engine: improved pysheds HAND/bathtub forced by Ida MRMS QPE
- Primary JSON: `figures/product_assets/risk_depth_assets.json`
- Nested case study: `risk_depth_assets_south_queens.json`
- UI: Scenario risk card with extent switcher on `figures/product_map.html`

Research bands (≥3 / ≥8 / ≥15 cm) are **not** NWS criteria.

## Hazard catalog hooks

`figures/product_assets/hazard_catalog.json`:

| Source | Status |
| --- | --- |
| MRMS QPE Ida | available (local fixtures) |
| Open Earth2-class scenario | available (local) |
| ERA5 precip | hook (CDS fetch hint) |
| GFS precip | hook (NOMADS/AWS fetch hint) |

No Earth2Studio Enterprise / HENS.

## Serve

```bash
python scripts/serve_product.py
# http://127.0.0.1:8765/product_map.html
```

GitHub: https://github.com/jesscmiel/nyc-flood-impact
