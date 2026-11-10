# Exposure v1 — citywide GeoPackage

- File: `figures/product_assets/exposure_citywide.gpkg` (layers: `roads`, `stations`, `facilities`)
- Meta: `exposure_citywide.json`
- Depth intersects: `exposure_depth_intersects.json` (reliable raster sampling)
- UI: Facilities toggle (`lyFac`) + roads/stations — feature counts must be numeric (no `err`)

Build: `python scripts/build_exposure_gpkg.py` then `python scripts/build_risk_tables.py`
