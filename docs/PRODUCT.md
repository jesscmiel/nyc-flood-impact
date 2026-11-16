# Asset Decision Desk — product one-pager

**Research replay** for Hurricane Ida (NYC). Not NWS. Not decision-grade.

## Cold start (offline fixtures)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python scripts/serve_product.py   # → http://127.0.0.1:8765/product_map.html
```

**Offline UI chrome:** Leaflet + brand fonts are vendored under `figures/vendor/` (no Google Fonts / unpkg). Fixture JSON lives in `fixtures/ida_v1/` + `figures/product_assets/`. A local **paper basemap** always draws; optional Esri streets need network (Storm layers → Online streets).

```bash
# Re-download vendor assets (maintainers / CI bootstrap)
make vendor
(cd figures/vendor && sha256sum -c SHA256SUMS)
(cd fixtures/ida_v1 && sha256sum -c SHA256SUMS)
```

See [RELEASE.md](./RELEASE.md) for `demo-ida-v1` tag instructions.

## Defaults (60s demo)

- Shortlist from `config/demo_shortlist.yaml` (Smith-9 · Van Wyck · Brooklyn Hospital Downtown · Myrtle)
- Light desk bundle first; All/search lazy-loads full inventory
- FloodNet drawer closed; access overlay off; single map key
- HAND screening cm vs FloodNet street peaks honesty chip
- All-mode = decision classes; schools opt-in
- SFINCS Advanced only — non-peer banner + HAND auto-dim
- Henri Event switch available after `make henri-parity` (radar + official inventory + shortlist + compare strip)

## Rebuild DAG (Decision Desk)

```
DEM → MRMS → drainage proxy → HAND depth → exposure GPKG
  → build_decision_desk_assets → expand_ida_access_replay_pack
  → build_engine_disagreement → apply_desk_demo_curation
  → make henri-parity (optional second storm)
  → relativize_product_paths → vendor (once) → html (make html)
```

`make desk` / `make html` / `make henri-parity` / `make test` / `make access-pack` / `make disagreement` / `make vendor` / `make demo-tag`.
