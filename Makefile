PYTHON ?= python3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate
E2S_PYTHON ?= /home/jesscmiel/projects/earth2studio/.venv/bin/python

.PHONY: help setup install map validation live-ida live clean

help:
	@echo "Targets: setup install map validation live-ida live clean"
	@echo "Earth2Studio is a dependency — use E2S_PYTHON for GPU forecasts."

setup:
	$(PYTHON) -m venv $(VENV)

install:
	$(ACTIVATE) && python -m pip install -U pip && python -m pip install -e .

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
