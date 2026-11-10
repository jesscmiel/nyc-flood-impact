# Flood risk MVP scaffold

Open-stack **flood risk** product direction. NYC / Ida is a **case study** only.

**Out of scope:** Earth2Studio Enterprise, HENS, official NWS warning issuance.

## Intended modules (stubs)

| Module | Role |
| --- | --- |
| `hazard/` | Storm / precip / hydro forcing (MRMS, ERA5, GFS; open FCN/StormCast if installable) |
| `inundation/` | Depth / extent engines (pysheds now; SFINCS / LISFLOOD-FP candidates) |
| `exposure/` | Roads, stations, buildings, critical facilities |
| `risk/` | Scenario + return-period metrics, disruption scores |
| `validate/` | Obs overlays (311, gauges, NFHL) — skill, not certification |

See the store doc `flood-risk-product-reset.md` for architecture and prioritized MVP steps.

## Run the current case-study UI

```bash
python scripts/serve_product.py
# open http://127.0.0.1:8765/product_map.html
```

Do **not** open the HTML via `file://` — GeoJSON fetches will fail.
