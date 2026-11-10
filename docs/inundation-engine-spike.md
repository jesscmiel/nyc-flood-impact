# Inundation engine spike (SFINCS / LISFLOOD-FP)

**Date:** 2026-11-10 · **Case study:** South Queens + Ida MRMS QPE  
**Constraint:** no Earth2Studio Enterprise / HENS

## Result

| Engine | Installable here | Runnable | Notes |
| --- | --- | --- | --- |
| **LISFLOOD-FP** | No | No | No pip wheel; no binary on PATH |
| **SFINCS** | Schema only (`hydromt-sfincs` 1.2.2) | No | Latest GitHub release has **no Linux binary assets**; `sfincs` not on PATH |
| **pysheds** | Yes | Yes | MVP engine — improved borough HAND/bathtub |

`hydromt-sfincs` wrote a **schema-only** model under `outputs/sfincs_spike_queens/` (`sfincs.inp` + gis). That is **not** a completed inundation run.

Machine-readable: `outputs/inundation_engine_spike.json` / `figures/product_assets/inundation_engine_spike.json`.

## Fallback delivered

- Improved pysheds borough spike: `depth_south_queens_mrms_qpe_ida_*`
- Depth×asset risk table: `risk_depth_assets.json` (roads / stations / facilities by depth band)
- UI **Scenario risk card** on `product_map.html`

## Unblock path (later)

1. Obtain/compile official SFINCS Linux binary (or container) and place on PATH  
2. Or build LISFLOOD-FP from source and wrap a runner in `flood_risk/inundation/`  
3. Re-force South Queens DEM with Ida rain and compare vs pysheds bands
