#!/usr/bin/env python3
"""Fetch FloodNet sensor metadata + flooding events; extract Ida product window.

Sources (NYC Open Data):
  - kb2e-tjy3  FloodNet: Sensor Deployment Metadata
  - aq7i-eu5q  FloodNet: Street Flooding Events Measured by FloodNet Sensors

Zenodo minute timeseries (sep-2021) is preferred when reachable; this machine may
see Zenodo 403 — NYC Open Data event timeseries still covers Ida peaks.

Writes:
  data/raw/floodnet/floodnet_sensor_metadata.csv
  data/raw/floodnet/floodnet_flooding_events.csv
  data/processed/floodnet/floodnet_ida_events.geojson
  data/processed/floodnet/floodnet_ida_fetch_meta.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_risk.validate.floodnet import IDA_END_UTC, IDA_INIT_UTC, build_ida_events

RAW = ROOT / "data" / "raw" / "floodnet"
PROCESSED = ROOT / "data" / "processed" / "floodnet"

META_URL = "https://data.cityofnewyork.us/api/views/kb2e-tjy3/rows.csv?accessType=DOWNLOAD"
EVENTS_URL = "https://data.cityofnewyork.us/api/views/aq7i-eu5q/rows.csv?accessType=DOWNLOAD"
ZENODO_SEP_URL = (
    "https://zenodo.org/records/10211443/files/floodnet-flood-sensor-sep-2021.csv?download=1"
)
UA = "nyc-flood-impact/1.0 (research; FloodNet Ida validation)"


def _download(url: str, dest: Path, *, timeout: int = 180) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        status = getattr(resp, "status", 200)
    dest.write_bytes(data)
    return {"url": url, "path": str(dest), "bytes": len(data), "http_status": status}


def main() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    meta_path = RAW / "floodnet_sensor_metadata.csv"
    events_path = RAW / "floodnet_flooding_events.csv"
    zenodo_path = RAW / "floodnet-flood-sensor-sep-2021.csv"

    downloads: dict[str, dict] = {}
    for label, url, path in (
        ("sensor_metadata", META_URL, meta_path),
        ("flooding_events", EVENTS_URL, events_path),
    ):
        if path.exists() and path.stat().st_size > 1000:
            downloads[label] = {
                "url": url,
                "path": str(path),
                "bytes": path.stat().st_size,
                "cached": True,
            }
        else:
            downloads[label] = _download(url, path)
            downloads[label]["cached"] = False

    zenodo: dict = {"url": ZENODO_SEP_URL, "available": False}
    if zenodo_path.exists() and zenodo_path.stat().st_size > 1000:
        zenodo.update(
            {
                "available": True,
                "path": str(zenodo_path),
                "bytes": zenodo_path.stat().st_size,
                "cached": True,
            }
        )
    else:
        try:
            info = _download(ZENODO_SEP_URL, zenodo_path, timeout=120)
            zenodo.update({"available": True, **info, "cached": False})
        except Exception as exc:  # noqa: BLE001 — document gap honestly
            zenodo.update({"available": False, "error": f"{type(exc).__name__}: {exc}"})

    fc = build_ida_events(events_csv=events_path, metadata_csv=meta_path)
    out_geo = PROCESSED / "floodnet_ida_events.geojson"
    # Drop bulky series from a slim stations index used by map overlays; keep full in processed.
    out_geo.write_text(json.dumps(fc, indent=2))

    stations_slim = {
        "type": "FeatureCollection",
        "name": "floodnet_ida_stations",
        "features": [
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    k: v
                    for k, v in f["properties"].items()
                    if k not in ("depth_series_in", "depth_series_s")
                },
            }
            for f in fc["features"]
        ],
        "properties": {
            **(fc.get("properties") or {}),
            "series_stripped": True,
            "full_events_geojson": str(out_geo),
        },
    }
    slim_path = PROCESSED / "floodnet_ida_stations.geojson"
    slim_path.write_text(json.dumps(stations_slim, indent=2))

    meta = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_start_utc": IDA_INIT_UTC.isoformat().replace("+00:00", "Z"),
        "window_end_utc": IDA_END_UTC.isoformat().replace("+00:00", "Z"),
        "downloads": downloads,
        "zenodo_sep_2021": zenodo,
        "n_ida_events": (fc.get("properties") or {}).get("n_events"),
        "n_ida_sensors": (fc.get("properties") or {}).get("n_sensors"),
        "outputs": {
            "events_geojson": str(out_geo),
            "stations_geojson": str(slim_path),
        },
        "gaps": []
        if (fc.get("properties") or {}).get("n_events")
        else ["No FloodNet events overlapping Ida window — check Open Data freshness."],
    }
    if not zenodo.get("available"):
        meta["gaps"].append(
            "Zenodo minute timeseries (floodnet-flood-sensor-sep-2021.csv) unavailable; "
            "using NYC Open Data event time-series depth values instead."
        )
    (PROCESSED / "floodnet_ida_fetch_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"wrote": str(out_geo), **{k: meta[k] for k in ("n_ida_events", "n_ida_sensors", "gaps")}}, indent=2))
    return meta


if __name__ == "__main__":
    main()
