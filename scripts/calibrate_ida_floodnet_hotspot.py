#!/usr/bin/env python3
"""Calibrate FloodNet Ida hotspot hydro (transparent scale+bias on excess ponding).

Does NOT rescale primary HAND citywide. Writes reproduction skill card + station
GeoJSON for the product map Advanced validation panel.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.validate.ida_hotspot import (  # noqa: E402
    calibrate_ida_hotspot,
    stations_geojson,
)
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
FN = PROCESSED_DIR / "floodnet"
DRAIN = PROCESSED_DIR / "drainage_capacity"


def _ensure_events() -> Path:
    events = FN / "floodnet_ida_events.geojson"
    if events.exists() and events.stat().st_size > 50:
        return events
    from fetch_floodnet_ida import main as fetch_main

    fetch_main()
    if not events.exists():
        raise FileNotFoundError(f"FloodNet Ida extract missing: {events}")
    return events


def main() -> dict:
    events = _ensure_events()
    excess = DRAIN / "excess_precip_mm.tif"
    if not excess.exists():
        raise FileNotFoundError(f"Excess precip missing (run drainage proxy): {excess}")

    primary = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not primary.exists():
        primary = INUN / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    nest = INUN / "depth_hand_nest_10m_south_queens_ida_m.tif"
    sfincs = INUN / "depth_sfincs_queens_ida_m.tif"

    report = calibrate_ida_hotspot(
        events_geojson=events,
        excess_precip_tif=excess,
        primary_hand_tif=primary if primary.exists() else None,
        nest_hand_tif=nest if nest.exists() else None,
        sfincs_tif=sfincs if sfincs.exists() else None,
    )
    geo = stations_geojson(report)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    FN.mkdir(parents=True, exist_ok=True)

    out_json = OUTPUTS_DIR / "ida_floodnet_reproduction.json"
    payload = json.dumps(report, indent=2)
    out_json.write_text(payload)
    (ASSETS / "ida_floodnet_reproduction.json").write_text(payload)
    (FN / "ida_floodnet_reproduction.json").write_text(payload)

    geo_txt = json.dumps(geo, indent=2)
    (OUTPUTS_DIR / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)
    (ASSETS / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)
    (FN / "floodnet_ida_hotspot_stations.geojson").write_text(geo_txt)

    # Keep primary FloodNet validation card; add reproduction keys to manifests.
    hot = report["summary"]["hotspot_calibrated"]
    hand = report["summary"]["primary_hand"]
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["ida_event_reproduction"] = {
            "scores": "ida_floodnet_reproduction.json",
            "stations_geojson": "floodnet_ida_hotspot_stations.geojson",
            "engine": report["engine"],
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
                "primary_hand_rmse_m": hand.get("rmse_m"),
                "loo_rmse_m": (report.get("leave_one_out") or {}).get("rmse_m"),
            },
            "lead_with": report["lead_with"],
            "do_not_lead_with": report["do_not_lead_with"],
            "demo_honesty": report["demo_honesty"],
        }
        dash = m.get("validation_dashboard") or {}
        dash.update(
            {
                "ida_reproduction": "ida_floodnet_reproduction.json",
                "lead_metric": "floodnet_hotspot_rmse_bias_residual",
                "bury_311_hit_rate": True,
            }
        )
        m["validation_dashboard"] = dash
        mp.write_text(json.dumps(m, indent=2))

    # Refresh HTML so Advanced panel picks up new assets (same path as desk builder).
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
    except Exception as exc:  # noqa: BLE001 — wire is best-effort
        print(json.dumps({"html_refresh_warning": str(exc)}))

    summary = {
        "wrote": str(out_json),
        "n_sensors": report["summary"]["n_sensors"],
        "scale": report["calibration"]["scale"],
        "bias_m": report["calibration"]["bias_m"],
        "hotspot_rmse_m": hot.get("rmse_m"),
        "hotspot_bias_m": hot.get("bias_m"),
        "hotspot_oom_ok": f"{hot.get('oom_ok_n')}/{hot.get('n')}",
        "primary_hand_rmse_m": hand.get("rmse_m"),
        "loo_rmse_m": (report.get("leave_one_out") or {}).get("rmse_m"),
    }
    print(json.dumps(summary, indent=2))
    return report


if __name__ == "__main__":
    main()
