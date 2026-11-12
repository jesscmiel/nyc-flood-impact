# FloodNet raw cache (local)

Regenerate with:

```bash
.venv/bin/python scripts/fetch_floodnet_ida.py
```

Downloads (gitignored except this README):

- `floodnet_sensor_metadata.csv` — NYC Open Data `kb2e-tjy3`
- `floodnet_flooding_events.csv` — NYC Open Data `aq7i-eu5q`
- `floodnet-flood-sensor-sep-2021.csv` — Zenodo minute timeseries (optional; may 403)

Ida window extract + skill card live under `data/processed/floodnet/` and `outputs/floodnet_validation.json`.
