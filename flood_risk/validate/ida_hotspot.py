"""FloodNet Ida hotspot hydro — transparent bias/scale on local excess ponding.

Primary metro HAND is often dry at FloodNet posts (stream HAND ≫ street rain).
This module does NOT rescale HAND citywide. It fits a labeled local ponding
proxy so Ida peak depths at the sparse 2021 FloodNet posts are
order-of-magnitude right, and reports residual error honestly.

Research only — NOT NWS / NOT decision-grade / NOT citywide perfection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.sample import sample_gen
from rasterio.warp import transform as warp_transform

from flood_risk.inundation.hand_bathtub import RUNOFF_COEFF
from flood_risk.validate.floodnet import (
    HENRI_INIT_UTC,
    IDA_INIT_UTC,
    _nearest_wet,
    _sample_xy,
    collapse_max_peak_per_sensor,
)

ENGINE_ID = "floodnet_ida_hotspot_hydro_v1"
ENGINE_LABEL = "FloodNet Ida hotspot hydro (excess-precip ponding × linear calib)"
ENGINE_ID_DEEPEN = "floodnet_magnitude_deepen_v1"
ENGINE_LABEL_DEEPEN = (
    "FloodNet magnitude deepen (Ida fit + Henri holdout transfer; pooled when data allows)"
)


def _sample_any(ds: rasterio.io.DatasetReader, lon: float, lat: float) -> float:
    """Sample lon/lat, reprojecting when the raster is not EPSG:4326."""
    crs = ds.crs
    if crs is not None and (crs.to_epsg() or 0) != 4326 and "4326" not in str(crs).upper():
        xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
        vals = list(sample_gen(ds, [(xs[0], ys[0])]))
        if not vals:
            return float("nan")
        v = float(vals[0][0])
        if ds.nodata is not None and v == ds.nodata:
            return float("nan")
        if not np.isfinite(v) or v < -100:
            return float("nan")
        return v
    return _sample_xy(ds, lon, lat, nodata_as_zero=False)


def ponding_predictor_m(excess_precip_mm: float, *, runoff_coeff: float = RUNOFF_COEFF) -> float:
    """Street-scale ponding proxy: runoff × excess precip (ignores stream HAND)."""
    if not np.isfinite(excess_precip_mm):
        return float("nan")
    return float(runoff_coeff * float(excess_precip_mm) / 1000.0)


def fit_scale_bias(
    predictors: np.ndarray,
    obs: np.ndarray,
) -> dict[str, Any]:
    """Least-squares depth = scale * x + bias (clipped ≥0 after apply)."""
    x = np.asarray(predictors, dtype=np.float64)
    y = np.asarray(obs, dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 2:
        return {
            "scale": 1.0,
            "bias_m": 0.0,
            "n_fit": int(mask.sum()),
            "fit_ok": False,
            "method": "identity_fallback",
        }
    A = np.column_stack([x[mask], np.ones(int(mask.sum()), dtype=np.float64)])
    coef, residuals, rank, singular = np.linalg.lstsq(A, y[mask], rcond=None)
    scale = float(coef[0])
    bias = float(coef[1])
    pred = np.clip(scale * x + bias, 0.0, None)
    resid = pred - y
    resid_m = resid[mask]
    return {
        "scale": scale,
        "bias_m": bias,
        "n_fit": int(mask.sum()),
        "fit_ok": True,
        "method": "ols_scale_bias_clip0",
        "formula": "depth_m = max(0, scale * runoff_coeff * excess_precip_mm/1000 + bias_m)",
        "runoff_coeff": RUNOFF_COEFF,
        "in_sample_rmse_m": float(np.sqrt(np.mean(resid_m**2))),
        "in_sample_bias_m": float(np.mean(resid_m)),
        "in_sample_mae_m": float(np.mean(np.abs(resid_m))),
        "lstsq_rank": int(rank),
    }


def leave_one_out_residuals(
    predictors: np.ndarray,
    obs: np.ndarray,
) -> dict[str, Any]:
    """Leave-one-out CV — honesty check for n≈5 in-sample fit."""
    x = np.asarray(predictors, dtype=np.float64)
    y = np.asarray(obs, dtype=np.float64)
    n = int(x.size)
    preds = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        if int(mask.sum()) < 2 or not (np.isfinite(x[i]) and np.isfinite(y[i])):
            continue
        fit = fit_scale_bias(x[mask], y[mask])
        preds[i] = max(0.0, fit["scale"] * float(x[i]) + fit["bias_m"])
    resid = preds - y
    ok = np.isfinite(resid)
    if not ok.any():
        return {"n": 0, "rmse_m": None, "bias_m": None, "mae_m": None, "residuals_m": []}
    r = resid[ok]
    return {
        "n": int(ok.sum()),
        "rmse_m": float(np.sqrt(np.mean(r**2))),
        "bias_m": float(np.mean(r)),
        "mae_m": float(np.mean(np.abs(r))),
        "residuals_m": [None if not np.isfinite(v) else float(v) for v in resid],
        "loo_predictions_m": [None if not np.isfinite(v) else float(v) for v in preds],
    }


def _oom_ok(obs_m: float, model_m: float) -> bool:
    """Order-of-magnitude: same decade for ≥5 cm peaks, or abs err ≤5 cm for tiny peaks.

    Dry / near-dry model (≤5 mm) never counts as OOM — that is the HAND failure mode.
    """
    if not (np.isfinite(obs_m) and np.isfinite(model_m)):
        return False
    if model_m < 0.005:
        return False
    if obs_m < 0.05:
        return abs(model_m - obs_m) <= 0.05
    ratio = model_m / obs_m
    return 0.1 <= ratio <= 10.0


def calibrate_ida_hotspot(
    *,
    events_geojson: Path | dict[str, Any],
    excess_precip_tif: Path,
    primary_hand_tif: Path | None = None,
    nest_hand_tif: Path | None = None,
    sfincs_tif: Path | None = None,
    init_time_utc: datetime = IDA_INIT_UTC,
) -> dict[str, Any]:
    """Fit hotspot hydro at FloodNet Ida posts; score vs primary HAND / nest / SFINCS."""
    if isinstance(events_geojson, Path):
        fc = json.loads(events_geojson.read_text())
    else:
        fc = events_geojson

    features = list(fc.get("features") or [])
    station_rows: list[dict[str, Any]] = []
    xs: list[float] = []
    ys: list[float] = []

    with rasterio.open(excess_precip_tif) as excess_ds:
        hand_ds = rasterio.open(primary_hand_tif) if primary_hand_tif and Path(primary_hand_tif).exists() else None
        nest_ds = rasterio.open(nest_hand_tif) if nest_hand_tif and Path(nest_hand_tif).exists() else None
        sfincs_ds = rasterio.open(sfincs_tif) if sfincs_tif and Path(sfincs_tif).exists() else None
        try:
            for feat in features:
                props = feat.get("properties") or {}
                lon = float(props.get("lon", feat["geometry"]["coordinates"][0]))
                lat = float(props.get("lat", feat["geometry"]["coordinates"][1]))
                obs = props.get("max_depth_m")
                if obs is None and props.get("max_depth_in") is not None:
                    obs = float(props["max_depth_in"]) * 0.0254
                if obs is None or not np.isfinite(float(obs)):
                    continue
                obs_m = float(obs)
                excess_mm = _sample_any(excess_ds, lon, lat)
                if not np.isfinite(excess_mm):
                    # treat nodata excess as 0 for predictor honesty
                    excess_mm = 0.0
                x = ponding_predictor_m(excess_mm)
                hand_m = _sample_xy(hand_ds, lon, lat) if hand_ds is not None else float("nan")
                hand_near = (
                    _nearest_wet(hand_ds, lon, lat, search_m=250.0) if hand_ds is not None else {}
                )
                nest_m = _sample_any(nest_ds, lon, lat) if nest_ds is not None else float("nan")
                if nest_ds is not None and (not np.isfinite(nest_m) or nest_m < 0):
                    nest_m = 0.0
                sfincs_m = _sample_any(sfincs_ds, lon, lat) if sfincs_ds is not None else float("nan")
                if sfincs_ds is not None and (not np.isfinite(sfincs_m) or sfincs_m < 0):
                    sfincs_m = float("nan")

                xs.append(x)
                ys.append(obs_m)
                station_rows.append(
                    {
                        "sensor_id": props.get("sensor_id"),
                        "sensor_name": props.get("sensor_name"),
                        "borough": props.get("borough"),
                        "lon": lon,
                        "lat": lat,
                        "obs_peak_m": obs_m,
                        "obs_peak_lead_h": props.get("peak_lead_h"),
                        "excess_precip_mm": float(excess_mm),
                        "ponding_predictor_m": float(x),
                        "primary_hand_m": None if not np.isfinite(hand_m) else float(hand_m),
                        "primary_hand_nearest_wet_250m": hand_near,
                        "hand_nest_10m_m": None if not np.isfinite(nest_m) else float(nest_m),
                        "sfincs_queens_m": None if not np.isfinite(sfincs_m) else float(sfincs_m),
                    }
                )
        finally:
            if hand_ds is not None:
                hand_ds.close()
            if nest_ds is not None:
                nest_ds.close()
            if sfincs_ds is not None:
                sfincs_ds.close()

    x_a = np.asarray(xs, dtype=np.float64)
    y_a = np.asarray(ys, dtype=np.float64)
    fit = fit_scale_bias(x_a, y_a)
    loo = leave_one_out_residuals(x_a, y_a)

    cal_depths = np.clip(fit["scale"] * x_a + fit["bias_m"], 0.0, None)
    for i, row in enumerate(station_rows):
        cal = float(cal_depths[i])
        obs_m = float(row["obs_peak_m"])
        hand = row["primary_hand_m"]
        hand_f = float(hand) if hand is not None and np.isfinite(hand) else 0.0
        nest = row["hand_nest_10m_m"]
        nest_f = float(nest) if nest is not None and np.isfinite(nest) else float("nan")
        sf = row["sfincs_queens_m"]
        sf_f = float(sf) if sf is not None and np.isfinite(sf) else float("nan")
        row.update(
            {
                "hotspot_cal_m": cal,
                "residual_m": cal - obs_m,
                "abs_error_m": abs(cal - obs_m),
                "ratio_cal_obs": (cal / obs_m) if obs_m > 1e-9 else None,
                "oom_ok": _oom_ok(obs_m, cal),
                "primary_hand_residual_m": hand_f - obs_m,
                "hand_nest_residual_m": None if not np.isfinite(nest_f) else nest_f - obs_m,
                "sfincs_residual_m": None if not np.isfinite(sf_f) else sf_f - obs_m,
                "sfincs_oom_ok": None if not np.isfinite(sf_f) else _oom_ok(obs_m, sf_f),
            }
        )

    def _peak_stats(model: np.ndarray, obs: np.ndarray | None = None) -> dict[str, Any]:
        obs_use = y_a if obs is None else np.asarray(obs, dtype=np.float64)
        model_use = np.asarray(model, dtype=np.float64)
        if model_use.shape != obs_use.shape:
            return {"n": 0, "rmse_m": None, "bias_m": None, "mae_m": None, "oom_ok_n": 0}
        mask = np.isfinite(model_use) & np.isfinite(obs_use)
        if not mask.any():
            return {"n": 0, "rmse_m": None, "bias_m": None, "mae_m": None, "oom_ok_n": 0}
        resid = model_use[mask] - obs_use[mask]
        oom = sum(
            1 for o, m in zip(obs_use[mask], model_use[mask]) if _oom_ok(float(o), float(m))
        )
        return {
            "n": int(mask.sum()),
            "rmse_m": float(np.sqrt(np.mean(resid**2))),
            "bias_m": float(np.mean(resid)),
            "mae_m": float(np.mean(np.abs(resid))),
            "model_mean_m": float(np.mean(model_use[mask])),
            "model_max_m": float(np.max(model_use[mask])),
            "oom_ok_n": int(oom),
            "oom_ok_fraction": float(oom / int(mask.sum())),
        }

    hand_arr = np.asarray(
        [0.0 if r["primary_hand_m"] is None else float(r["primary_hand_m"]) for r in station_rows],
        dtype=np.float64,
    )
    nest_arr = np.asarray(
        [
            np.nan if r["hand_nest_10m_m"] is None else float(r["hand_nest_10m_m"])
            for r in station_rows
        ],
        dtype=np.float64,
    )
    sfincs_arr = np.asarray(
        [
            np.nan if r["sfincs_queens_m"] is None else float(r["sfincs_queens_m"])
            for r in station_rows
        ],
        dtype=np.float64,
    )

    queens = [r for r in station_rows if (r.get("borough") or "").lower() == "queens"]
    queens_sf = np.asarray(
        [float(r["sfincs_queens_m"]) for r in queens if r.get("sfincs_queens_m") is not None],
        dtype=np.float64,
    )
    queens_obs = np.asarray(
        [float(r["obs_peak_m"]) for r in queens if r.get("sfincs_queens_m") is not None],
        dtype=np.float64,
    )

    return {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "certified_skill": False,
        "citywide_perfection": False,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": ENGINE_ID,
        "engine_label": ENGINE_LABEL,
        "init_time_utc": init_time_utc.isoformat().replace("+00:00", "Z"),
        "goal": "first_step_reproduce_ida_at_floodnet_posts",
        "not_goal": "citywide_hand_perfection",
        "predictor": {
            "name": "local_excess_precip_ponding",
            "runoff_coeff": RUNOFF_COEFF,
            "excess_precip_tif": str(excess_precip_tif),
            "note": (
                "Ignores stream HAND at the post. Primary HAND is dry when HAND ≫ rain; "
                "street sensors often sit off the HAND wet channel."
            ),
        },
        "calibration": fit,
        "leave_one_out": loo,
        "in_sample_note": (
            "Scale/bias fitted on the same n FloodNet Ida peaks scored below — in-sample. "
            "Leave-one-out RMSE is the honesty check. Do not claim out-of-event skill."
        ),
        "summary": {
            "n_sensors": len(station_rows),
            "obs_peak_mean_m": float(np.mean(y_a)) if y_a.size else None,
            "obs_peak_max_m": float(np.max(y_a)) if y_a.size else None,
            "primary_hand": _peak_stats(hand_arr),
            "hand_nest_10m": _peak_stats(nest_arr),
            "sfincs_queens_all_posts": _peak_stats(sfincs_arr),
            "sfincs_queens_borough_posts": (
                _peak_stats(queens_sf, queens_obs)
                if queens_sf.size and queens_obs.size == queens_sf.size
                else {"n": 0, "rmse_m": None, "bias_m": None, "mae_m": None, "oom_ok_n": 0}
            ),
            "hotspot_calibrated": _peak_stats(cal_depths),
            "queens_sfincs_obs_pairs": [
                {
                    "sensor_id": r["sensor_id"],
                    "obs_m": r["obs_peak_m"],
                    "sfincs_m": r["sfincs_queens_m"],
                }
                for r in queens
            ],
        },
        "stations": station_rows,
        "demo_honesty": (
            "Primary product depth remains metro HAND (cm-scale screening). "
            "Hotspot hydro is a transparent FloodNet-post calibration for Ida reproduction only — "
            "not DEP / not SWMM / not citywide depth / not decision-grade. "
            "SFINCS Queens may already be OOM at Queens posts without calib; Brooklyn posts need hotspot."
        ),
        "lead_with": [
            "FloodNet hotspot peak RMSE / bias after transparent scale+bias",
            "residual table vs obs at each Ida sensor",
            "primary HAND still dry / cm-scale at posts (unchanged)",
        ],
        "do_not_lead_with": ["311_hit_rate", "citywide_hand_rescaled"],
    }


def stations_geojson(report: dict[str, Any]) -> dict[str, Any]:
    """GeoJSON of FloodNet posts with obs / cal / residual for map overlay."""
    feats = []
    for row in report.get("stations") or []:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": {
                    k: row.get(k)
                    for k in (
                        "sensor_id",
                        "sensor_name",
                        "borough",
                        "obs_peak_m",
                        "hotspot_cal_m",
                        "residual_m",
                        "abs_error_m",
                        "ratio_cal_obs",
                        "oom_ok",
                        "primary_hand_m",
                        "hand_nest_10m_m",
                        "sfincs_queens_m",
                        "excess_precip_mm",
                        "ponding_predictor_m",
                    )
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "floodnet_ida_hotspot_stations",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "properties": {
            "engine": report.get("engine"),
            "calibration": report.get("calibration"),
            "official_nws": False,
            "decision_grade": False,
            "role": "ida_event_reproduction_overlay",
        },
        "features": feats,
    }


def _load_peak_rows(
    events_geojson: Path | dict[str, Any],
    excess_precip_tif: Path,
    *,
    event_id: str,
    collapse: bool = True,
) -> list[dict[str, Any]]:
    """Sample ponding predictors at FloodNet peaks for one storm window."""
    if isinstance(events_geojson, Path):
        fc = json.loads(Path(events_geojson).read_text())
    else:
        fc = events_geojson
    if collapse:
        fc = collapse_max_peak_per_sensor(fc)

    rows: list[dict[str, Any]] = []
    with rasterio.open(excess_precip_tif) as excess_ds:
        for feat in fc.get("features") or []:
            props = feat.get("properties") or {}
            lon = float(props.get("lon", feat["geometry"]["coordinates"][0]))
            lat = float(props.get("lat", feat["geometry"]["coordinates"][1]))
            obs = props.get("max_depth_m")
            if obs is None and props.get("max_depth_in") is not None:
                obs = float(props["max_depth_in"]) * 0.0254
            if obs is None or not np.isfinite(float(obs)):
                continue
            excess_mm = _sample_any(excess_ds, lon, lat)
            if not np.isfinite(excess_mm):
                excess_mm = 0.0
            x = ponding_predictor_m(excess_mm)
            rows.append(
                {
                    "event_id": event_id,
                    "sensor_id": props.get("sensor_id"),
                    "sensor_name": props.get("sensor_name"),
                    "borough": props.get("borough"),
                    "lon": lon,
                    "lat": lat,
                    "obs_peak_m": float(obs),
                    "obs_peak_lead_h": props.get("peak_lead_h"),
                    "excess_precip_mm": float(excess_mm),
                    "ponding_predictor_m": float(x),
                }
            )
    return rows


def apply_scale_bias(
    rows: list[dict[str, Any]],
    *,
    scale: float,
    bias_m: float,
) -> list[dict[str, Any]]:
    """Attach calibrated depths / residuals / OOM flags using fixed coeffs."""
    out: list[dict[str, Any]] = []
    for row in rows:
        x = float(row["ponding_predictor_m"])
        obs = float(row["obs_peak_m"])
        cal = max(0.0, scale * x + bias_m)
        updated = dict(row)
        updated.update(
            {
                "hotspot_cal_m": cal,
                "residual_m": cal - obs,
                "abs_error_m": abs(cal - obs),
                "ratio_cal_obs": (cal / obs) if obs > 1e-9 else None,
                "oom_ok": _oom_ok(obs, cal),
            }
        )
        out.append(updated)
    return out


def _peak_stats_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "rmse_m": None, "bias_m": None, "mae_m": None, "oom_ok_n": 0}
    obs = np.asarray([r["obs_peak_m"] for r in rows], dtype=np.float64)
    cal = np.asarray([r["hotspot_cal_m"] for r in rows], dtype=np.float64)
    resid = cal - obs
    oom = sum(1 for r in rows if r.get("oom_ok"))
    return {
        "n": len(rows),
        "rmse_m": float(np.sqrt(np.mean(resid**2))),
        "bias_m": float(np.mean(resid)),
        "mae_m": float(np.mean(np.abs(resid))),
        "model_mean_m": float(np.mean(cal)),
        "model_max_m": float(np.max(cal)),
        "oom_ok_n": int(oom),
        "oom_ok_fraction": float(oom / len(rows)),
    }


def deepen_magnitude_calibration(
    *,
    ida_events_geojson: Path | dict[str, Any],
    ida_excess_precip_tif: Path,
    henri_events_geojson: Path | dict[str, Any] | None = None,
    henri_excess_precip_tif: Path | None = None,
    ida_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deepen beyond Ida's 5-post fit when a second storm (Henri) has FloodNet + excess precip.

    - Keeps Ida in-sample hotspot as the Decision Desk residual table.
    - Transfers Ida scale/bias to Henri max-per-sensor peaks (holdout).
    - Fits a pooled scale/bias on unique sensor peaks across Ida+Henri when n>5.
    - Later FloodNet archive without storm-matched excess precip is documented as unavailable.
    """
    if ida_report is None:
        ida_report = calibrate_ida_hotspot(
            events_geojson=ida_events_geojson,
            excess_precip_tif=ida_excess_precip_tif,
        )

    ida_fit = ida_report["calibration"]
    ida_rows = _load_peak_rows(ida_events_geojson, ida_excess_precip_tif, event_id="ida-2021")
    ida_scored = apply_scale_bias(
        ida_rows, scale=float(ida_fit["scale"]), bias_m=float(ida_fit["bias_m"])
    )

    henri_available = bool(
        henri_events_geojson is not None
        and henri_excess_precip_tif is not None
        and Path(henri_excess_precip_tif).exists()
    )
    henri_rows: list[dict[str, Any]] = []
    henri_transfer: list[dict[str, Any]] = []
    henri_transfer_stats: dict[str, Any] = {
        "n": 0,
        "rmse_m": None,
        "bias_m": None,
        "mae_m": None,
        "oom_ok_n": 0,
    }
    if henri_available:
        henri_rows = _load_peak_rows(
            henri_events_geojson,  # type: ignore[arg-type]
            Path(henri_excess_precip_tif),  # type: ignore[arg-type]
            event_id="henri-2021",
        )
        henri_transfer = apply_scale_bias(
            henri_rows, scale=float(ida_fit["scale"]), bias_m=float(ida_fit["bias_m"])
        )
        henri_transfer_stats = _peak_stats_rows(henri_transfer)

    # Pooled unique sensors: prefer Ida peak when a sensor appears in both storms.
    by_sensor: dict[str, dict[str, Any]] = {}
    for row in henri_rows:
        sid = str(row.get("sensor_id") or "")
        if sid:
            by_sensor[sid] = dict(row)
    for row in ida_rows:
        sid = str(row.get("sensor_id") or "")
        if sid:
            by_sensor[sid] = dict(row)
    pooled_rows = list(by_sensor.values())
    pooled_x = np.asarray([r["ponding_predictor_m"] for r in pooled_rows], dtype=np.float64)
    pooled_y = np.asarray([r["obs_peak_m"] for r in pooled_rows], dtype=np.float64)
    pooled_fit = fit_scale_bias(pooled_x, pooled_y) if len(pooled_rows) >= 2 else {
        "scale": ida_fit["scale"],
        "bias_m": ida_fit["bias_m"],
        "n_fit": len(pooled_rows),
        "fit_ok": False,
        "method": "ida_fallback",
    }
    pooled_loo = leave_one_out_residuals(pooled_x, pooled_y) if len(pooled_rows) >= 3 else {
        "n": 0,
        "rmse_m": None,
        "bias_m": None,
        "mae_m": None,
    }
    pooled_scored = apply_scale_bias(
        pooled_rows,
        scale=float(pooled_fit["scale"]),
        bias_m=float(pooled_fit["bias_m"]),
    )
    new_henri_only = [
        r for r in henri_rows if str(r.get("sensor_id")) not in {str(x.get("sensor_id")) for x in ida_rows}
    ]

    deepen = {
        "engine": ENGINE_ID_DEEPEN,
        "engine_label": ENGINE_LABEL_DEEPEN,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "official_nws": False,
        "decision_grade": False,
        "certified_skill": False,
        "primary_depth_unchanged": True,
        "ida_fit_n": int(ida_fit.get("n_fit") or 0),
        "ida_in_sample": ida_report.get("summary", {}).get("hotspot_calibrated"),
        "ida_leave_one_out": ida_report.get("leave_one_out"),
        "henri_holdout": {
            "available": henri_available,
            "init_time_utc": HENRI_INIT_UTC.isoformat().replace("+00:00", "Z"),
            "transfer_from": "ida_scale_bias",
            "scale": ida_fit.get("scale"),
            "bias_m": ida_fit.get("bias_m"),
            "n_events_raw_note": "Henri window collapsed to max peak per sensor before scoring",
            "n_sensors": len(henri_rows),
            "n_new_vs_ida": len(new_henri_only),
            "new_sensor_ids": [r.get("sensor_id") for r in new_henri_only],
            "stats": henri_transfer_stats,
            "stations": henri_transfer,
        },
        "pooled_unique_sensors": {
            "n_fit": int(pooled_fit.get("n_fit") or 0),
            "beyond_ida_5": int(pooled_fit.get("n_fit") or 0) > 5,
            "calibration": pooled_fit,
            "leave_one_out": pooled_loo,
            "in_sample": _peak_stats_rows(pooled_scored),
            "stations": pooled_scored,
            "note": (
                "Pooled unique FloodNet posts across Ida+Henri (Ida peak preferred on overlap). "
                "Still sparse — not citywide / not decision-grade."
            ),
        },
        "later_floodnet_archive": {
            "usable_for_magnitude_calib": False,
            "reason": (
                "Post-Ida archive (hundreds of sensors) lacks storm-matched MRMS excess-precip "
                "rasters in this product — peaks alone cannot deepen the ponding scale/bias."
            ),
        },
        "lead_with": [
            "Ida hotspot RMSE (desk residual table, n=5)",
            "Henri holdout transfer RMSE when available",
            "Pooled unique-sensor n when >5",
        ],
        "do_not_lead_with": ["311_hit_rate", "later_floodnet_peak_counts_as_skill"],
        "demo_honesty": (
            "Ida Decision Desk peaks stay the n=5 hotspot fit. Henri is a transparent holdout "
            "transfer of the same scale/bias; pooled n>5 only when Henri adds posts. "
            "Primary HAND unchanged. NOT NWS / NOT decision-grade."
        ),
    }

    # Attach deepen block onto a copy of the Ida report for a single skill card.
    out = dict(ida_report)
    out["magnitude_deepen"] = deepen
    out["engine_deepen"] = ENGINE_ID_DEEPEN
    summary = dict(out.get("summary") or {})
    summary["magnitude_deepen"] = {
        "henri_holdout_n": henri_transfer_stats.get("n"),
        "henri_holdout_rmse_m": henri_transfer_stats.get("rmse_m"),
        "henri_holdout_bias_m": henri_transfer_stats.get("bias_m"),
        "henri_holdout_oom_ok_n": henri_transfer_stats.get("oom_ok_n"),
        "pooled_n": pooled_fit.get("n_fit"),
        "pooled_beyond_ida_5": int(pooled_fit.get("n_fit") or 0) > 5,
        "pooled_rmse_m": (_peak_stats_rows(pooled_scored) or {}).get("rmse_m"),
        "pooled_loo_rmse_m": pooled_loo.get("rmse_m"),
    }
    out["summary"] = summary
    return out
