#!/usr/bin/env python3
"""Score FloodNet Ida events vs primary metro HAND depth (RMSE / bias / timing).

Never leads with 311 hit≈1 — FloodNet magnitude + timing are the headline metrics.
Writes outputs/floodnet_validation.json + product_assets copies.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.validate.floodnet import (  # noqa: E402
    DEFAULT_CUM_LEADS_H,
    IDA_INIT_UTC,
    score_floodnet_vs_primary,
)
from nyc_flash_flood_case_study.config import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
FN = PROCESSED_DIR / "floodnet"


def _ensure_ida_events() -> Path:
    events = FN / "floodnet_ida_events.geojson"
    if events.exists() and events.stat().st_size > 50:
        return events
    from fetch_floodnet_ida import main as fetch_main

    fetch_main()
    if not events.exists():
        raise FileNotFoundError(f"FloodNet Ida extract missing after fetch: {events}")
    return events


def main() -> dict:
    events = _ensure_ida_events()
    storm = INUN / "depth_metro_mrms_qpe_ida_storm_total_m.tif"
    if not storm.exists():
        storm = INUN / "depth_citywide_mrms_qpe_ida_storm_total_m.tif"
    if not storm.exists():
        raise FileNotFoundError(f"Primary depth storm-total missing: {storm}")

    cum: dict[int, Path] = {}
    for lh in DEFAULT_CUM_LEADS_H:
        p = INUN / f"depth_metro_mrms_cum_lead_{int(lh):02d}h_m.tif"
        if p.exists():
            cum[int(lh)] = p

    report = score_floodnet_vs_primary(
        events_geojson=events,
        depth_storm_total_tif=storm,
        cum_depth_tif_by_lead=cum,
        init_time_utc=IDA_INIT_UTC,
        cum_leads_h=sorted(cum) or list(DEFAULT_CUM_LEADS_H),
    )

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    FN.mkdir(parents=True, exist_ok=True)

    out_json = OUTPUTS_DIR / "floodnet_validation.json"
    out_json.write_text(json.dumps(report, indent=2))
    (ASSETS / "floodnet_validation.json").write_text(json.dumps(report, indent=2))
    (FN / "floodnet_validation.json").write_text(json.dumps(report, indent=2))

    stations = FN / "floodnet_ida_stations.geojson"
    if stations.exists():
        shutil.copy2(stations, ASSETS / "floodnet_ida_stations.geojson")
    fetch_meta = FN / "floodnet_ida_fetch_meta.json"
    if fetch_meta.exists():
        shutil.copy2(fetch_meta, ASSETS / "floodnet_ida_fetch_meta.json")

    # Wire product manifests — FloodNet first; 311 buried.
    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["validation_floodnet"] = {
            "scores": "floodnet_validation.json",
            "stations_geojson": "floodnet_ida_stations.geojson",
            "role": "magnitude_timing_primary_reference",
            "official": False,
            "certified_skill": False,
            "lead_with": report["lead_with"],
            "do_not_lead_with": report["do_not_lead_with"],
            "summary": {
                "n_events": report["summary"]["n_events"],
                "n_sensors": report["summary"]["n_sensors"],
                "peak_rmse_m": report["summary"]["peak_rmse_m"],
                "peak_bias_mean_m": (report["summary"]["peak_bias_m"] or {}).get("mean"),
                "timing_error_mean_h": (report["summary"]["timing_error_h"] or {}).get("mean"),
            },
        }
        dash = m.get("validation_dashboard") or {}
        dash.update(
            {
                "floodnet": "floodnet_validation.json",
                "lead_metric": "floodnet_peak_rmse_bias_timing",
                "bury_311_hit_rate": True,
                "official": False,
                "certified_skill": False,
            }
        )
        m["validation_dashboard"] = dash
        mp.write_text(json.dumps(m, indent=2))

    print(
        json.dumps(
            {
                "wrote": str(out_json),
                "n_events": report["summary"]["n_events"],
                "n_sensors": report["summary"]["n_sensors"],
                "peak_rmse_m": report["summary"]["peak_rmse_m"],
                "peak_bias_mean_m": (report["summary"]["peak_bias_m"] or {}).get("mean"),
                "timing_error_mean_h": (report["summary"]["timing_error_h"] or {}).get("mean"),
                "obs_peak_max_m": report["summary"]["obs_peak_max_m"],
                "model_peak_max_m": report["summary"]["model_peak_max_m"],
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    main()
