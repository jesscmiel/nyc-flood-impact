PYTHON ?= python3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate
E2S_PYTHON ?= /home/jesscmiel/projects/earth2studio/.venv/bin/python
DEMO_TAG ?= demo-ida-v1

.PHONY: help setup install map validation live-ida live clean desk html access-pack disagreement henri-parity corridor denser-drains nest-exchange live-mrms relativize vendor test ci-guard demo-tag

help:
	@echo "Decision Desk: desk html henri-parity corridor denser-drains nest-exchange live-mrms vendor test demo-tag"
	@echo "Legacy: validation live-ida live clean"
	@echo "Earth2Studio is a dependency — use E2S_PYTHON for GPU forecasts."

setup:
	$(PYTHON) -m venv $(VENV)

install:
	$(ACTIVATE) && python -m pip install -U pip && python -m pip install -e ".[test]"

# Rebuild ranked desk + access demotion (needs depth TIF + exposure GPKG)
desk:
	$(ACTIVATE) && python scripts/build_decision_desk_assets.py
	$(ACTIVATE) && python scripts/expand_ida_access_replay_pack.py
	$(ACTIVATE) && python scripts/apply_desk_demo_curation.py

# Expand labeled synthetic Ida access pack + re-join
access-pack:
	$(ACTIVATE) && python scripts/expand_ida_access_replay_pack.py

# HAND vs SFINCS non-peer disagreement chips (shortlist + top-100)
disagreement:
	$(ACTIVATE) && python scripts/build_engine_disagreement.py

# Full Henri Event parity (radar + official inventory desk + shortlist + compare)
henri-parity:
	$(ACTIVATE) && python scripts/build_henri_parity.py

# P2.3 research corridor impassability (LION × HAND; not DOT closures)
corridor:
	$(ACTIVATE) && python scripts/build_corridor_impassability.py

# P2.5 denser open catch-basin inventory for capacity proxy (not SWMM)
denser-drains:
	$(ACTIVATE) && python scripts/build_denser_drain_inventory.py

# Vendor Leaflet + fonts for offline serve
vendor:
	$(ACTIVATE) && python scripts/vendor_static_assets.py

# Regenerate product_map.html from current manifest
html:
	$(ACTIVATE) && python -c "import json,sys; from pathlib import Path; \
sys.path.insert(0,'scripts'); from product_map_html import write_product_html; \
from nyc_flash_flood_case_study.config import FIGURES_DIR; \
A=FIGURES_DIR/'product_assets'; \
m=json.loads((A/'product_manifest.json').read_text()); \
p=json.loads((A/'pluvial_meta.json').read_text()) if (A/'pluvial_meta.json').exists() else {}; \
v=json.loads((A/'validation_product.json').read_text()) if (A/'validation_product.json').exists() else {}; \
print(write_product_html(m,p,v))"

relativize:
	$(ACTIVATE) && python scripts/relativize_product_paths.py

test:
	$(ACTIVATE) && python -m pytest tests/ -q --tb=short

ci-guard: test
	$(ACTIVATE) && python scripts/relativize_product_paths.py

# Annotated local tag for demo pack (does not push). See docs/RELEASE.md.
# Ignores untracked local data/outputs; fails only on modified/staged tracked files.
demo-tag:
	@test -z "$$(git status --porcelain --untracked-files=no)" || (echo "Tracked files dirty — commit or stash before tagging."; exit 1)
	@git rev-parse "$(DEMO_TAG)" >/dev/null 2>&1 && (echo "Tag $(DEMO_TAG) already exists locally."; exit 1) || true
	git tag -a "$(DEMO_TAG)" -m "Ida Decision Desk demo pack v1 (research fixtures + vendored UI)"
	@echo "Created annotated tag $(DEMO_TAG). Publish with: git push origin $(DEMO_TAG)"

# Track 3/5 product map from existing Ida assets
map:
	$(ACTIVATE) && python scripts/build_product_map.py

# Track 5 only
validation:
	$(ACTIVATE) && python scripts/run_validation_report.py

# Track 4: rebuild map from existing Ida clipped forecast (no new GPU run)
live-ida:
	$(ACTIVATE) && python scripts/run_live_pipeline.py --skip-forecast --with-mrms-qa

# Track 4: live-ish forecast (requires earth2studio in E2S_PYTHON env)
# Example: make live INIT=2021-09-01T12:00:00
INIT ?= 2021-09-01T12:00:00
live:
	$(E2S_PYTHON) scripts/run_earth2_forecast.py --init-time $(INIT) --steps 4 --members 1 \
		--output data/forecasts/earth2_precip_live.nc
	$(ACTIVATE) && python -c "from nyc_flash_flood_case_study.forecast import normalize_earth2_forecast; \
print(normalize_earth2_forecast('data/forecasts/earth2_precip_live.nc','data/forecasts/nyc_precip_live.nc'))"
	$(ACTIVATE) && python scripts/build_ida_v0_map.py --skip-normalize --skip-infra \
		--clipped-forecast data/forecasts/nyc_precip_live.nc --with-mrms-qa || true
	$(ACTIVATE) && python scripts/build_product_map.py

clean:
	rm -rf $(VENV) outputs/validation_product.json outputs/live_pipeline_meta.json

# P2.6 feathered nested SFINCS exchange + non-peer HAND calib (Advanced only)
nest-exchange:
	$(ACTIVATE) && python scripts/build_sfincs_nest_exchange.py

# P2.7 live MRMS QPE probe + fixture honesty status
live-mrms:
	$(ACTIVATE) && python scripts/build_live_mrms_path.py
