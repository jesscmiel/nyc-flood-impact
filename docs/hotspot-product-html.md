# Hotspot product HTML — FloodNet Ida in Decision Desk

**Branch:** `cursor/hotspot-product-html-1fa4`  
**Demo:** [product_map.html](../figures/product_map.html)

FloodNet hotspot Ida reproduction is wired into the **working** Asset Decision Desk (core panel, default-on posts) — not Advanced-only.

## Honesty

- Primary desk depth remains metro HAND (cm-scale screening).
- FloodNet panel = separate post-level hotspot hydro; in-sample RMSE ~0.21 m, LOO ~0.32 m, OOM 5/5.
- Does **not** rescale citywide HAND. Not DEP / SWMM / decision-grade / NWS.

## Deliverables

| Deliverable | Path |
| --- | --- |
| Decision Desk HTML | `figures/product_map.html` |
| Asset root | `figures/product_assets/` |
| Hotspot skill card | `figures/product_assets/ida_floodnet_reproduction.json` |
| Post overlay | `figures/product_assets/floodnet_ida_hotspot_stations.geojson` |
| Manifest | `figures/product_assets/manifest.json` (`ida_event_reproduction`) |
| Desk assets | `figures/product_assets/decision_desk_assets.json` · `.geojson` |
| Method / residuals | `docs/ida-event-reproduction.md` |
| HTML generator | `scripts/product_map_html.py` |

Serve: `python scripts/serve_product.py`
