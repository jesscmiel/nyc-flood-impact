"""Unit tests for FloodNet magnitude deepen (Ida fit + Henri holdout)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from flood_risk.risk.live_access_feeds import BUS_TIME_SKIPPED
from flood_risk.validate.floodnet import collapse_max_peak_per_sensor
from flood_risk.validate.ida_hotspot import (
    deepen_magnitude_calibration,
    fit_scale_bias,
    ponding_predictor_m,
)


def _write_excess(path: Path, values: dict[tuple[float, float], float]) -> None:
    """Tiny 4×4 grid; sample known lon/lat cells with given excess mm."""
    # cells centered near NYC sample points
    transform = from_origin(-74.01, 40.70, 0.01, 0.01)
    data = np.zeros((4, 4), dtype=np.float32)
    for (lon, lat), mm in values.items():
        # approx col/row for from_origin
        col = int((lon - (-74.01)) / 0.01)
        row = int((40.70 - lat) / 0.01)
        if 0 <= row < 4 and 0 <= col < 4:
            data[row, col] = mm
    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(data, 1)


def _fc(points: list[dict]) -> dict:
    feats = []
    for p in points:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                "properties": p,
            }
        )
    return {"type": "FeatureCollection", "features": feats, "properties": {}}


def test_collapse_max_peak_per_sensor():
    fc = _fc(
        [
            {"sensor_id": "A", "lon": -74.0, "lat": 40.68, "max_depth_m": 0.2},
            {"sensor_id": "A", "lon": -74.0, "lat": 40.68, "max_depth_m": 0.5},
            {"sensor_id": "B", "lon": -73.99, "lat": 40.69, "max_depth_m": 0.1},
        ]
    )
    out = collapse_max_peak_per_sensor(fc)
    assert out["properties"]["n_sensors"] == 2
    by_id = {f["properties"]["sensor_id"]: f["properties"]["max_depth_m"] for f in out["features"]}
    assert by_id["A"] == 0.5
    assert by_id["B"] == 0.1


def test_deepen_adds_henri_holdout_and_pooled_beyond_5(tmp_path: Path):
    # Five Ida posts + two Henri-only posts → pooled n=7
    ida_pts = [
        {"sensor_id": f"I{i}", "lon": -74.005 + 0.01 * i, "lat": 40.685, "max_depth_m": 0.1 * (i + 1)}
        for i in range(5)
    ]
    henri_pts = [
        {"sensor_id": "I0", "lon": -74.005, "lat": 40.685, "max_depth_m": 0.15},  # overlap
        {"sensor_id": "H1", "lon": -73.98, "lat": 40.69, "max_depth_m": 0.22},
        {"sensor_id": "H2", "lon": -73.97, "lat": 40.695, "max_depth_m": 0.18},
    ]
    # Put large excess so predictors are finite / distinct
    vals = {(p["lon"], p["lat"]): 80.0 + 10 * i for i, p in enumerate(ida_pts + henri_pts)}
    ida_tif = tmp_path / "ida_excess.tif"
    henri_tif = tmp_path / "henri_excess.tif"
    _write_excess(ida_tif, vals)
    _write_excess(henri_tif, vals)

    report = deepen_magnitude_calibration(
        ida_events_geojson=_fc(ida_pts),
        ida_excess_precip_tif=ida_tif,
        henri_events_geojson=_fc(henri_pts),
        henri_excess_precip_tif=henri_tif,
    )
    deep = report["magnitude_deepen"]
    assert deep["henri_holdout"]["available"] is True
    assert deep["henri_holdout"]["n_sensors"] == 3
    assert deep["henri_holdout"]["stats"]["n"] == 3
    assert deep["henri_holdout"]["stats"]["rmse_m"] is not None
    pooled = deep["pooled_unique_sensors"]
    assert pooled["beyond_ida_5"] is True
    assert pooled["n_fit"] == 7
    assert report["summary"]["magnitude_deepen"]["pooled_beyond_ida_5"] is True


def test_fit_scale_bias_and_predictor_sane():
    x = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    y = 2.0 * x + 0.01
    fit = fit_scale_bias(x, y)
    assert fit["fit_ok"] is True
    assert abs(fit["scale"] - 2.0) < 1e-6
    assert abs(fit["bias_m"] - 0.01) < 1e-6
    assert ponding_predictor_m(100.0) > 0


def test_bus_time_skipped_constant():
    assert BUS_TIME_SKIPPED["status"] == "skipped"
    assert BUS_TIME_SKIPPED["env_var"] == "MTA_BUS_TIME_API_KEY"
