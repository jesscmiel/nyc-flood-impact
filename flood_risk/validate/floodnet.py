"""FloodNet street-sensor magnitude + timing skill vs primary HAND depth.

Research validation only — NOT certified skill / NOT NWS / NOT decision-grade.
Prefer FloodNet RMSE/bias/timing over 311 hit-rate for magnitude claims.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.sample import sample_gen

INCH_TO_M = 0.0254
IDA_INIT_UTC = datetime(2021, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
IDA_END_UTC = datetime(2021, 9, 3, 0, 0, 0, tzinfo=timezone.utc)
HENRI_INIT_UTC = datetime(2021, 8, 21, 18, 0, 0, tzinfo=timezone.utc)
HENRI_END_UTC = datetime(2021, 8, 23, 0, 0, 0, tzinfo=timezone.utc)
DEFAULT_CUM_LEADS_H = (0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36)


def parse_floodnet_gmt(value: str) -> datetime:
    """Parse NYC Open Data FloodNet GMT timestamps (MM/DD/YYYY h:mm:ss AM/PM)."""
    dt = datetime.strptime(value.strip(), "%m/%d/%Y %I:%M:%S %p")
    return dt.replace(tzinfo=timezone.utc)


def parse_installed_date(value: str) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _safe_literal_list(raw: str) -> list[float]:
    if not raw or not str(raw).strip():
        return []
    try:
        vals = ast.literal_eval(str(raw))
    except (SyntaxError, ValueError):
        return []
    if not isinstance(vals, (list, tuple)):
        return []
    out: list[float] = []
    for v in vals:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(float("nan"))
    return out


def _sample_xy(
    ds: rasterio.io.DatasetReader,
    lon: float,
    lat: float,
    *,
    nodata_as_zero: bool = True,
) -> float:
    """Sample depth at lon/lat.

    Primary HAND products encode dry land as nodata (−9999). For magnitude
    validation that means model depth ≈ 0 m at the sensor — not a missing
    sample — so ``nodata_as_zero`` defaults True.
    """
    vals = list(sample_gen(ds, [(lon, lat)]))
    if not vals:
        return float("nan")
    v = float(vals[0][0])
    if ds.nodata is not None and v == ds.nodata:
        return 0.0 if nodata_as_zero else float("nan")
    if not np.isfinite(v) or v < -100:
        return 0.0 if nodata_as_zero else float("nan")
    return v


def _nearest_wet(
    ds: rasterio.io.DatasetReader,
    lon: float,
    lat: float,
    *,
    search_m: float = 250.0,
    wet_m: float = 0.005,
) -> dict[str, Any]:
    """Max wet depth within ~search_m of the sensor (HAND cell misalignment)."""
    from rasterio.transform import rowcol, xy

    row, col = rowcol(ds.transform, lon, lat)
    if not (0 <= row < ds.height and 0 <= col < ds.width):
        return {"depth_m": None, "dist_m": None, "lon": None, "lat": None}
    # ~deg per meter at NYC latitude
    m_per_deg_lat = 110540.0
    m_per_deg_lon = 111320.0 * float(np.cos(np.deg2rad(lat)))
    px_m = abs(ds.res[0]) * m_per_deg_lon
    py_m = abs(ds.res[1]) * m_per_deg_lat
    rad_x = max(1, int(np.ceil(search_m / max(px_m, 1e-6))))
    rad_y = max(1, int(np.ceil(search_m / max(py_m, 1e-6))))
    r0, r1 = max(0, row - rad_y), min(ds.height, row + rad_y + 1)
    c0, c1 = max(0, col - rad_x), min(ds.width, col + rad_x + 1)
    win = ds.read(1, window=((r0, r1), (c0, c1))).astype(np.float64)
    if ds.nodata is not None:
        win = np.where(win == ds.nodata, np.nan, win)
    win = np.where(win < -100, np.nan, win)
    best = None  # (depth, dist_m, rr, cc)
    for i in range(win.shape[0]):
        for j in range(win.shape[1]):
            d = win[i, j]
            if not np.isfinite(d) or d < wet_m:
                continue
            rr, cc = r0 + i, c0 + j
            x, y = xy(ds.transform, rr, cc, offset="center")
            dist = float(
                np.hypot((float(x) - lon) * m_per_deg_lon, (float(y) - lat) * m_per_deg_lat)
            )
            if dist > search_m:
                continue
            if best is None or d > best[0] or (d == best[0] and dist < best[1]):
                best = (float(d), dist, float(x), float(y))
    if best is None:
        return {"depth_m": None, "dist_m": None, "lon": None, "lat": None, "search_m": search_m}
    return {
        "depth_m": best[0],
        "dist_m": best[1],
        "lon": best[2],
        "lat": best[3],
        "search_m": search_m,
    }


def event_overlaps_window(
    start: datetime,
    end: datetime,
    *,
    window_start: datetime = IDA_INIT_UTC,
    window_end: datetime = IDA_END_UTC,
) -> bool:
    return end >= window_start and start <= window_end


def build_ida_events(
    *,
    events_csv: Path,
    metadata_csv: Path,
    window_start: datetime = IDA_INIT_UTC,
    window_end: datetime = IDA_END_UTC,
) -> dict[str, Any]:
    """Filter FloodNet flooding-events CSV to the Ida product window and join lat/lon."""
    import csv

    meta: dict[str, dict[str, str]] = {}
    with metadata_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sid = (row.get("Sensor ID") or "").strip()
            if sid:
                meta[sid] = row

    features: list[dict[str, Any]] = []
    skipped_no_meta = 0
    with events_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                start = parse_floodnet_gmt(row["Flood Start Datetime (GMT)"])
                end = parse_floodnet_gmt(row["Flood End Datetime (GMT)"])
            except (KeyError, ValueError):
                continue
            if not event_overlaps_window(start, end, window_start=window_start, window_end=window_end):
                continue
            sid = (row.get("Sensor ID") or "").strip()
            m = meta.get(sid)
            if m is None:
                skipped_no_meta += 1
                continue
            try:
                lat = float(m["Latitude"])
                lon = float(m["Longitude"])
            except (KeyError, TypeError, ValueError):
                skipped_no_meta += 1
                continue

            depths_in = _safe_literal_list(row.get("Time Series Depth Values (inches)") or "")
            stamps_s = _safe_literal_list(row.get("Time Series Depth Timestamps (seconds)") or "")
            max_in = float(row.get("Maximum Flood Depth (inches)") or "nan")
            ttm_min = float(row.get("Time to Maximum Flood Depth (minutes)") or "nan")
            peak_time = start + timedelta(minutes=ttm_min) if np.isfinite(ttm_min) else None
            if peak_time is None and depths_in and stamps_s:
                i_peak = int(np.nanargmax(np.asarray(depths_in, dtype=np.float64)))
                peak_time = start + timedelta(seconds=float(stamps_s[i_peak]))
                max_in = float(depths_in[i_peak])

            peak_lead_h = (
                (peak_time - window_start).total_seconds() / 3600.0 if peak_time is not None else None
            )
            props = {
                "sensor_id": sid,
                "sensor_name": row.get("Sensor Name") or m.get("Sensor Name"),
                "borough": m.get("Borough"),
                "street_name": m.get("Street Name"),
                "flood_start_utc": start.isoformat().replace("+00:00", "Z"),
                "flood_end_utc": end.isoformat().replace("+00:00", "Z"),
                "peak_time_utc": peak_time.isoformat().replace("+00:00", "Z") if peak_time else None,
                "peak_lead_h": peak_lead_h,
                "max_depth_in": max_in if np.isfinite(max_in) else None,
                "max_depth_m": (max_in * INCH_TO_M) if np.isfinite(max_in) else None,
                "time_to_max_min": ttm_min if np.isfinite(ttm_min) else None,
                "duration_min": float(row.get("Total Duration (minutes)") or "nan"),
                "tidally_influenced": m.get("Tidally Influenced"),
                "date_installed": m.get("Date Installed"),
                "date_removed": m.get("Date Removed"),
                "depth_series_in": depths_in,
                "depth_series_s": stamps_s,
                "lon": lon,
                "lat": lat,
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": props,
                }
            )

    name = "floodnet_ida_events"
    if window_start == HENRI_INIT_UTC and window_end == HENRI_END_UTC:
        name = "floodnet_henri_events"
    return {
        "type": "FeatureCollection",
        "name": name,
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "properties": {
            "source_events": str(events_csv),
            "source_metadata": str(metadata_csv),
            "window_start_utc": window_start.isoformat().replace("+00:00", "Z"),
            "window_end_utc": window_end.isoformat().replace("+00:00", "Z"),
            "n_events": len(features),
            "n_sensors": len({f["properties"]["sensor_id"] for f in features}),
            "skipped_no_meta": skipped_no_meta,
            "units_note": "FloodNet depths stored as inches in source; max_depth_m = inches * 0.0254",
            "license_note": (
                "FloodNet data via NYC Open Data (FloodNet: Street Flooding Events / Sensor Deployment Metadata). "
                "Review FloodNet data access terms before redistribution beyond research use."
            ),
        },
        "features": features,
    }


def collapse_max_peak_per_sensor(fc: dict[str, Any]) -> dict[str, Any]:
    """Keep one feature per sensor_id — the event with the largest max_depth_m."""
    best: dict[str, dict[str, Any]] = {}
    for feat in fc.get("features") or []:
        props = feat.get("properties") or {}
        sid = props.get("sensor_id")
        if not sid:
            continue
        depth = props.get("max_depth_m")
        if depth is None or not np.isfinite(float(depth)):
            continue
        prev = best.get(sid)
        if prev is None or float(depth) > float(prev["properties"]["max_depth_m"]):
            best[sid] = feat
    out = dict(fc)
    out["features"] = list(best.values())
    props = dict(fc.get("properties") or {})
    props["n_events"] = len(out["features"])
    props["n_sensors"] = len(out["features"])
    props["collapse"] = "max_peak_per_sensor"
    out["properties"] = props
    return out


def build_henri_events(
    *,
    events_csv: Path,
    metadata_csv: Path,
    window_start: datetime = HENRI_INIT_UTC,
    window_end: datetime = HENRI_END_UTC,
    collapse: bool = True,
) -> dict[str, Any]:
    """FloodNet events overlapping the Henri remnant window (holdout beyond Ida)."""
    fc = build_ida_events(
        events_csv=events_csv,
        metadata_csv=metadata_csv,
        window_start=window_start,
        window_end=window_end,
    )
    return collapse_max_peak_per_sensor(fc) if collapse else fc


def _nearest_cum_lead(lead_h: float, cum_leads: tuple[int, ...] | list[int]) -> int:
    arr = np.asarray(list(cum_leads), dtype=np.float64)
    return int(arr[int(np.argmin(np.abs(arr - lead_h)))])


def score_floodnet_vs_primary(
    *,
    events_geojson: Path | dict[str, Any],
    depth_storm_total_tif: Path,
    cum_depth_tif_by_lead: dict[int, Path],
    init_time_utc: datetime = IDA_INIT_UTC,
    cum_leads_h: tuple[int, ...] | list[int] | None = None,
) -> dict[str, Any]:
    """Collocate FloodNet Ida events vs primary HAND depth — peak RMSE/bias + timing."""
    if isinstance(events_geojson, Path):
        fc = json.loads(events_geojson.read_text())
    else:
        fc = events_geojson

    leads = list(cum_leads_h) if cum_leads_h is not None else sorted(cum_depth_tif_by_lead)
    if not leads:
        leads = list(DEFAULT_CUM_LEADS_H)

    open_ds: dict[int, rasterio.io.DatasetReader] = {}
    try:
        for lh in leads:
            p = cum_depth_tif_by_lead.get(int(lh))
            if p is not None and Path(p).exists():
                open_ds[int(lh)] = rasterio.open(p)

        with rasterio.open(depth_storm_total_tif) as storm_ds:
            station_rows: list[dict[str, Any]] = []
            peak_obs: list[float] = []
            peak_mod: list[float] = []
            peak_near_bias: list[float] = []
            timing_err_h: list[float] = []
            series_resid: list[float] = []
            n_model_dry = 0

            for feat in fc.get("features") or []:
                props = feat.get("properties") or {}
                lon = float(props["lon"] if "lon" in props else feat["geometry"]["coordinates"][0])
                lat = float(props["lat"] if "lat" in props else feat["geometry"]["coordinates"][1])
                obs_peak_m = props.get("max_depth_m")
                if obs_peak_m is None and props.get("max_depth_in") is not None:
                    obs_peak_m = float(props["max_depth_in"]) * INCH_TO_M
                if obs_peak_m is None or not np.isfinite(obs_peak_m):
                    continue

                storm_depth = _sample_xy(storm_ds, lon, lat)
                nearest_wet = _nearest_wet(storm_ds, lon, lat, search_m=250.0)
                timeline: list[dict[str, Any]] = []
                model_depths: list[float] = []
                for lh in leads:
                    ds = open_ds.get(int(lh))
                    d = _sample_xy(ds, lon, lat) if ds is not None else float("nan")
                    timeline.append({"lead_h": int(lh), "model_depth_m": None if not np.isfinite(d) else float(d)})
                    model_depths.append(d)

                wet_idx = [i for i, d in enumerate(model_depths) if np.isfinite(d) and d >= 0.005]
                if wet_idx:
                    i_peak = max(wet_idx, key=lambda i: model_depths[i])
                    model_peak_m = float(model_depths[i_peak])
                    model_peak_lead_h = float(leads[i_peak])
                else:
                    # Flat dry timeline → timing undefined (do not treat lead 0 as a peak).
                    finite_vals = [d for d in model_depths if np.isfinite(d)]
                    model_peak_m = float(max(finite_vals)) if finite_vals else float("nan")
                    model_peak_lead_h = float("nan")

                # Prefer storm-total sample as peak magnitude for screening HAND (monotonic cum until recession).
                model_peak_for_mag = (
                    float(storm_depth)
                    if np.isfinite(storm_depth)
                    else (model_peak_m if np.isfinite(model_peak_m) else float("nan"))
                )
                # Also track nearest-wet HAND depth for spatial misalignment honesty.
                model_near_wet = nearest_wet.get("depth_m")
                model_peak_near = (
                    float(model_near_wet)
                    if model_near_wet is not None and np.isfinite(float(model_near_wet))
                    else float("nan")
                )

                obs_peak_lead = props.get("peak_lead_h")
                if obs_peak_lead is None and props.get("peak_time_utc"):
                    pt = datetime.fromisoformat(str(props["peak_time_utc"]).replace("Z", "+00:00"))
                    obs_peak_lead = (pt - init_time_utc).total_seconds() / 3600.0

                timing = None
                if (
                    obs_peak_lead is not None
                    and np.isfinite(float(obs_peak_lead))
                    and np.isfinite(model_peak_lead_h)
                ):
                    timing = float(model_peak_lead_h - float(obs_peak_lead))
                    timing_err_h.append(timing)

                if np.isfinite(model_peak_for_mag):
                    peak_obs.append(float(obs_peak_m))
                    peak_mod.append(float(model_peak_for_mag))
                    if model_peak_for_mag < 0.005:
                        n_model_dry += 1
                if np.isfinite(model_peak_near):
                    peak_near_bias.append(float(model_peak_near - float(obs_peak_m)))

                # Series residuals at FloodNet sample times vs nearest cum HAND frame.
                depths_in = props.get("depth_series_in") or []
                stamps_s = props.get("depth_series_s") or []
                start_s = props.get("flood_start_utc")
                if start_s and depths_in and stamps_s and open_ds:
                    start = datetime.fromisoformat(str(start_s).replace("Z", "+00:00"))
                    for sec, din in zip(stamps_s, depths_in):
                        try:
                            obs_m = float(din) * INCH_TO_M
                            t = start + timedelta(seconds=float(sec))
                        except (TypeError, ValueError):
                            continue
                        lead = (t - init_time_utc).total_seconds() / 3600.0
                        if lead < min(leads) - 1.5 or lead > max(leads) + 1.5:
                            continue
                        nearest = _nearest_cum_lead(lead, leads)
                        ds = open_ds.get(nearest)
                        if ds is None:
                            continue
                        mod = _sample_xy(ds, lon, lat)
                        if np.isfinite(mod) and np.isfinite(obs_m):
                            series_resid.append(float(mod - obs_m))

                near_bias = (
                    None
                    if not np.isfinite(model_peak_near)
                    else float(model_peak_near - float(obs_peak_m))
                )
                station_rows.append(
                    {
                        "sensor_id": props.get("sensor_id"),
                        "sensor_name": props.get("sensor_name"),
                        "borough": props.get("borough"),
                        "lon": lon,
                        "lat": lat,
                        "obs_peak_m": float(obs_peak_m),
                        "obs_peak_in": float(obs_peak_m) / INCH_TO_M,
                        "obs_peak_lead_h": None if obs_peak_lead is None else float(obs_peak_lead),
                        "model_storm_total_m": None if not np.isfinite(storm_depth) else float(storm_depth),
                        "model_peak_cum_m": None if not np.isfinite(model_peak_m) else model_peak_m,
                        "model_peak_lead_h": None if not np.isfinite(model_peak_lead_h) else model_peak_lead_h,
                        "model_dry_at_sensor": bool(
                            np.isfinite(model_peak_for_mag) and model_peak_for_mag < 0.005
                        ),
                        "nearest_wet_250m": nearest_wet,
                        "peak_bias_m": (
                            None
                            if not np.isfinite(model_peak_for_mag)
                            else float(model_peak_for_mag - float(obs_peak_m))
                        ),
                        "peak_bias_nearest_wet_m": near_bias,
                        "timing_error_h": timing,
                        "timing_undefined_reason": (
                            None
                            if timing is not None
                            else "model_dry_or_flat_at_sensor"
                        ),
                        "nearest_cum_lead_at_obs_peak": (
                            None
                            if obs_peak_lead is None
                            else _nearest_cum_lead(float(obs_peak_lead), leads)
                        ),
                        "timeline": timeline,
                    }
                )
    finally:
        for ds in open_ds.values():
            ds.close()

    peak_obs_a = np.asarray(peak_obs, dtype=np.float64)
    peak_mod_a = np.asarray(peak_mod, dtype=np.float64)
    peak_bias = peak_mod_a - peak_obs_a if peak_obs_a.size else np.asarray([], dtype=np.float64)
    timing_a = np.asarray(timing_err_h, dtype=np.float64)
    series_a = np.asarray(series_resid, dtype=np.float64)

    def _stats(arr: np.ndarray) -> dict[str, Any]:
        if arr.size == 0:
            return {"n": 0, "mean": None, "rmse": None, "mae": None, "min": None, "max": None}
        return {
            "n": int(arr.size),
            "mean": float(np.mean(arr)),
            "rmse": float(np.sqrt(np.mean(arr**2))),
            "mae": float(np.mean(np.abs(arr))),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }

    peak_rmse = float(np.sqrt(np.mean(peak_bias**2))) if peak_bias.size else None
    near_a = np.asarray(peak_near_bias, dtype=np.float64)
    summary = {
        "n_events": len(station_rows),
        "n_sensors": len({r["sensor_id"] for r in station_rows}),
        "boroughs": sorted({r["borough"] for r in station_rows if r.get("borough")}),
        "n_model_dry_at_sensor": n_model_dry,
        "obs_peak_mean_m": float(np.mean(peak_obs_a)) if peak_obs_a.size else None,
        "obs_peak_max_m": float(np.max(peak_obs_a)) if peak_obs_a.size else None,
        "model_peak_mean_m": float(np.mean(peak_mod_a)) if peak_mod_a.size else None,
        "model_peak_max_m": float(np.max(peak_mod_a)) if peak_mod_a.size else None,
        "peak_bias_m": _stats(peak_bias),
        "peak_rmse_m": peak_rmse,
        "peak_bias_nearest_wet_250m": _stats(near_a),
        "timing_error_h": _stats(timing_a),
        "timing_note": (
            "Timing only scored when the HAND cum timeline is wet (≥5 mm) at the sensor. "
            "Dry/flat model timelines leave timing undefined."
        ),
        "series_bias_m": _stats(series_a),
        "magnitude_gap_note": (
            "Primary HAND peaks are cm-scale; FloodNet Ida street peaks reach tens of cm to ~0.9 m. "
            "Large negative bias is expected and is the magnitude-honesty signal — do not rescale HAND "
            "with ad-hoc multipliers to match sensors."
        ),
    }

    return {
        "product": "flood_risk_research_prototype",
        "official_nws": False,
        "decision_grade": False,
        "certified_skill": False,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference": "floodnet_street_sensors",
        "compare_to": "primary_metro_hand_depth",
        "init_time_utc": init_time_utc.isoformat().replace("+00:00", "Z"),
        "depth_storm_total_tif": str(depth_storm_total_tif),
        "cum_leads_h": leads,
        "lead_with": [
            "FloodNet peak RMSE / mean bias (m)",
            "FloodNet peak timing error (h, model cum peak lead − sensor peak lead)",
            "series bias at FloodNet samples vs nearest cum HAND frame",
        ],
        "do_not_lead_with": ["311_hit_rate"],
        "summary": summary,
        "stations": station_rows,
        "honesty": (
            "FloodNet magnitude + timing vs research HAND screening depth. "
            "Pilot sensor coverage for Ida (few stations active in 2021). "
            "NOT certified verification skill. NOT NWS. NOT decision-grade. "
            "311 hit-rates are spatial-only and must not lead product copy."
        ),
    }
