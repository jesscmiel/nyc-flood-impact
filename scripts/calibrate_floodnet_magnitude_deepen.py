#!/usr/bin/env python3
"""Deepen FloodNet magnitude calibration beyond Ida's 5-post hotspot.

Uses Henri remnant FloodNet peaks (when MRMS excess precip is available) as a
holdout transfer of the Ida scale/bias, and a pooled unique-sensor fit when
n>5. Does NOT rescale primary HAND. Later FloodNet archive without storm-
matched precip is documented as unavailable for magnitude calib.

Writes:
  outputs/ida_floodnet_reproduction.json (+ product_assets copy)
  outputs/floodnet_magnitude_deepen.json
  data/processed/floodnet/floodnet_henri_events.geojson
  data/processed/drainage_capacity/excess_precip_henri_mm.tif
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DEFAULT_EVENT_DURATION_HR,
    EFFECTIVE_DRAINAGE_HOURS,
    effective_sink_mm,
)
from flood_risk.validate.floodnet import (  # noqa: E402
    HENRI_END_UTC,
    HENRI_INIT_UTC,
    build_henri_events,
)
from flood_risk.validate.ida_hotspot import (  # noqa: E402
    calibrate_ida_hotspot,
    deepen_magnitude_calibration,
    stations_geojson,
)
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
FN = PROCESSED_DIR / "floodnet"
DRAIN = PROCESSED_DIR / "drainage_capacity"
INUN = PROCESSED_DIR / "inundation"
RAW_FN = ROOT / "data" / "raw" / "floodnet"
HENRI_MRMS = PROCESSED_DIR / "mrms_qpe_metro_henri" / "mrms_qpe_metro_henri_storm_total.tif"
HENRI_DURATION_HR = max(
    DEFAULT_EVENT_DURATION_HR,
    (HENRI_END_UTC - HENRI_INIT_UTC).total_seconds() / 3600.0,
)


def _ensure_ida_events() -> Path:
    events = FN / "floodnet_ida_events.geojson"
    if events.exists() and events.stat().st_size > 50:
        return events
    from fetch_floodnet_ida import main as fetch_main

    fetch_main()
    if not events.exists():
        raise FileNotFoundError(f"FloodNet Ida extract missing: {events}")
    return events


def _ensure_raw_csvs() -> tuple[Path, Path]:
    meta = RAW_FN / "floodnet_sensor_metadata.csv"
    events = RAW_FN / "floodnet_flooding_events.csv"
    if meta.exists() and events.exists() and meta.stat().st_size > 100 and events.stat().st_size > 100:
        return events, meta
    from fetch_floodnet_ida import main as fetch_main

    fetch_main()
    if not (meta.exists() and events.exists()):
        raise FileNotFoundError("FloodNet raw CSVs missing after fetch")
    return events, meta


def build_henri_excess_precip() -> Path | None:
    """Write Henri excess precip on the metro drainage grid (same shape as Ida excess)."""
    out = DRAIN / "excess_precip_henri_mm.tif"
    cap_p = DRAIN / "drainage_capacity_mm_hr.tif"
    if not HENRI_MRMS.exists() or not cap_p.exists():
        return None
    with rasterio.open(HENRI_MRMS) as rain_ds, rasterio.open(cap_p) as cap_ds:
        rain = rain_ds.read(1).astype(np.float32)
        cap = cap_ds.read(1).astype(np.float32)
        profile = rain_ds.profile.copy()
        if rain.shape != cap.shape:
            # Align capacity to rain grid if needed (should match metro product).
            from rasterio.warp import reproject, Resampling

            cap_aligned = np.zeros(rain.shape, dtype=np.float32)
            reproject(
                source=cap,
                destination=cap_aligned,
                src_transform=cap_ds.transform,
                src_crs=cap_ds.crs,
                dst_transform=rain_ds.transform,
                dst_crs=rain_ds.crs,
                resampling=Resampling.bilinear,
            )
            cap = cap_aligned
        rain = np.where(~np.isfinite(rain) | (rain < 0), 0.0, rain)
        cap = np.where(~np.isfinite(cap) | (cap < 0), 0.0, cap)
        _, excess, _ = effective_sink_mm(
            rain,
            cap,
            duration_hr=HENRI_DURATION_HR,
            drainage_hours=EFFECTIVE_DRAINAGE_HOURS,
        )
        profile.update(dtype="float32", count=1, compress="deflate", nodata=None)
        DRAIN.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(excess.astype(np.float32), 1)
    meta = {
        "path": str(out),
        "source_rain": str(HENRI_MRMS),
        "capacity": str(cap_p),
        "duration_hr": HENRI_DURATION_HR,
        "drainage_hours": EFFECTIVE_DRAINAGE_HOURS,
        "engine": "drainage_capacity_proxy_v1",
        "event_id": "henri-2021",
    }
    (DRAIN / "excess_precip_henri_meta.json").write_text(json.dumps(meta, indent=2))
    return out


def _write_henri_events() -> Path:
    events_csv, meta_csv = _ensure_raw_csvs()
    fc = build_henri_events(events_csv=events_csv, metadata_csv=meta_csv, collapse=True)
    FN.mkdir(parents=True, exist_ok=True)
    out = FN / "floodnet_henri_events.geojson"
    out.write_text(json.dumps(fc, indent=2))
    (ASSETS / "floodnet_henri_events.geojson").write_text(out.read_text())
    return out


def main() -> dict:
    ida_events = _ensure_ida_events()
    ida_excess = DRAIN / "excess_precip_mm.tif"
    if not ida_excess.exists():
        raise FileNotFoundError(f"Ida excess precip missing: {ida_excess}")

    primary = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not primary.exists():
        primary = INUN / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    nest = INUN / "depth_hand_nest_10m_south_queens_ida_m.tif"
    sfincs = INUN / "depth_sfincs_queens_ida_m.tif"

    ida_report = calibrate_ida_hotspot(
        events_geojson=ida_events,
        excess_precip_tif=ida_excess,
        primary_hand_tif=primary if primary.exists() else None,
        nest_hand_tif=nest if nest.exists() else None,
        sfincs_tif=sfincs if sfincs.exists() else None,
    )

    henri_events = _write_henri_events()
    henri_excess = build_henri_excess_precip()

    report = deepen_magnitude_calibration(
        ida_events_geojson=ida_events,
        ida_excess_precip_tif=ida_excess,
        henri_events_geojson=henri_events if henri_events.exists() else None,
        henri_excess_precip_tif=henri_excess,
        ida_report=ida_report,
    )
    geo = stations_geojson(report)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    FN.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(report, indent=2)
    out_json = OUTPUTS_DIR / "ida_floodnet_reproduction.json"
    out_json.write_text(payload)
    (ASSETS / "ida_floodnet_reproduction.json").write_text(payload)
    (FN / "ida_floodnet_reproduction.json").write_text(payload)

    deepen_only = report.get("magnitude_deepen") or {}
    deepen_path = OUTPUTS_DIR / "floodnet_magnitude_deepen.json"
    deepen_txt = json.dumps(deepen_only, indent=2)
    deepen_path.write_text(deepen_txt)
    (ASSETS / "floodnet_magnitude_deepen.json").write_text(deepen_txt)
    (FN / "floodnet_magnitude_deepen.json").write_text(deepen_txt)

    geo_txt = json.dumps(geo, indent=2)
    (OUTPUTS_DIR / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)
    (ASSETS / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)
    (FN / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)

    hot = report["summary"]["hotspot_calibrated"]
    deepen_sum = report["summary"].get("magnitude_deepen") or {}
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["ida_event_reproduction"] = {
            "scores": "ida_floodnet_reproduction.json",
            "stations_geojson": "floodnet_ida_hotspot_stations.geojson",
            "engine": report["engine"],
            "engine_deepen": report.get("engine_deepen"),
            "magnitude_deepen": "floodnet_magnitude_deepen.json",
            "role": "floodnet_post_peak_reproduction",
            "primary_depth_unchanged": True,
            "official": False,
            "certified_skill": False,
            "citywide_perfection": False,
            "calibration": {
                "scale": report["calibration"]["scale"],
                "bias_m": report["calibration"]["bias_m"],
                "formula": report["calibration"].get("formula"),
                "n_fit": report["calibration"]["n_fit"],
            },
            "summary": {
                "n_sensors": report["summary"]["n_sensors"],
                "hotspot_rmse_m": hot.get("rmse_m"),
                "hotspot_bias_m": hot.get("bias_m"),
                "hotspot_oom_ok_n": hot.get("oom_ok_n"),
                "primary_hand_rmse_m": (report["summary"].get("primary_hand") or {}).get("rmse_m"),
                "loo_rmse_m": (report.get("leave_one_out") or {}).get("rmse_m"),
                "henri_holdout_n": deepen_sum.get("henri_holdout_n"),
                "henri_holdout_rmse_m": deepen_sum.get("henri_holdout_rmse_m"),
                "pooled_n": deepen_sum.get("pooled_n"),
                "pooled_beyond_ida_5": deepen_sum.get("pooled_beyond_ida_5"),
                "pooled_loo_rmse_m": deepen_sum.get("pooled_loo_rmse_m"),
            },
            "lead_with": report["lead_with"],
            "do_not_lead_with": report["do_not_lead_with"],
            "demo_honesty": (deepen_only.get("demo_honesty") or report.get("demo_honesty")),
        }
        dash = m.get("validation_dashboard") or {}
        dash.update(
            {
                "ida_reproduction": "ida_floodnet_reproduction.json",
                "floodnet_magnitude_deepen": "floodnet_magnitude_deepen.json",
                "lead_metric": "floodnet_hotspot_rmse_bias_residual",
                "bury_311_hit_rate": True,
            }
        )
        m["validation_dashboard"] = dash
        # Bus Time skip note lives on access feeds docs; keep a pointer on manifest.
        access = m.get("access_signals") or {}
        access["bus_time_vehicles"] = {
            "status": "skipped",
            "reason": "MTA Bus Time API key not configured in this environment",
            "env_var": "MTA_BUS_TIME_API_KEY",
            "note": (
                "Subway GTFS-RT VehiclePositions are keyless; Bus Time vehiclePositions "
                "requires a developer key. Live access path uses DOT speeds + 511-style "
                "closures + MTA service alerts only."
            ),
        }
        m["access_signals"] = access
        mp.write_text(json.dumps(m, indent=2))

    try:
        from product_map_html import write_product_html

        manifest = json.loads((ASSETS / "product_manifest.json").read_text())
        pluvial = (
            json.loads((ASSETS / "pluvial_meta.json").read_text())
            if (ASSETS / "pluvial_meta.json").exists()
            else {}
        )
        validation = (
            json.loads((ASSETS / "validation_product.json").read_text())
            if (ASSETS / "validation_product.json").exists()
            else {}
        )
        html_path = write_product_html(manifest, pluvial, validation)
        print(json.dumps({"html": str(html_path)}))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"html_refresh_warning": str(exc)}))

    summary = {
        "wrote": str(out_json),
        "deepen": str(deepen_path),
        "n_ida": report["summary"]["n_sensors"],
        "ida_rmse_m": hot.get("rmse_m"),
        "henri_holdout_n": deepen_sum.get("henri_holdout_n"),
        "henri_holdout_rmse_m": deepen_sum.get("henri_holdout_rmse_m"),
        "pooled_n": deepen_sum.get("pooled_n"),
        "pooled_beyond_ida_5": deepen_sum.get("pooled_beyond_ida_5"),
        "pooled_loo_rmse_m": deepen_sum.get("pooled_loo_rmse_m"),
        "henri_excess": str(henri_excess) if henri_excess else None,
    }
    print(json.dumps(summary, indent=2))
    return report


if __name__ == "__main__":
    main()
