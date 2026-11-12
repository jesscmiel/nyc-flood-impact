# Validation dashboard

**Lead metric:** FloodNet peak RMSE / bias / timing vs primary metro HAND — see [floodnet-validation.md](./floodnet-validation.md) and `figures/product_assets/floodnet_validation.json`.

- FloodNet skill card: `scripts/run_floodnet_validation.py`
- Exploratory 311 / AHPS hit rates (buried): `figures/product_assets/validation_scores.json` via `scripts/build_validation_dashboard.py`
- Map panel: limitations-first; prefers FloodNet RMSE/bias; **never leads with 311 hit-rate**

NOT NWS verification / NOT decision-grade.
