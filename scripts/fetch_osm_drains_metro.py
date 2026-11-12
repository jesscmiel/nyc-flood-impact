#!/usr/bin/env python3
"""Fetch metro-wide open drain / inlet points (DEP Open Data CSV + OSM cache).

Phase C of the robust flood-model plan. Prefers the NYC Open Data catch-basin
CSV download (SODA JSON pagination is flaky / 503). Optionally densifies with
cached OSM manhole/inlet GeoJSON. Never invents basins.

Writes:
  data/raw/infrastructure/osm_drains_metro.geojson   (merged open points)
  data/raw/infrastructure/nycdep_catch_basins_metro.csv
  data/raw/infrastructure/nycdep_catch_basins_metro.json  (summary / sample)
  data/raw/infrastructure/osm_drains_metro_fetch_meta.json
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nyc_flash_flood_case_study.config import RAW_DIR  # noqa: E402
from nyc_flash_flood_case_study.extents import EXTENTS  # noqa: E402

INFRA = RAW_DIR / "infrastructure"
BOUNDS = EXTENTS["metro"]["bounds"]
UA = "nyc-flood-impact/1.0 (research; metro drain inventory)"
DEP_CSV_URL = "https://data.cityofnewyork.us/api/views/2w2g-fk3i/rows.csv?accessType=DOWNLOAD"
POINT_RE = re.compile(
    r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _download(url: str, dest: Path, *, timeout: int = 300) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        status = getattr(resp, "status", 200)
    dest.write_bytes(data)
    return {"url": url, "path": str(dest), "bytes": len(data), "http_status": status}


def _parse_lon_lat(row: dict) -> tuple[float, float] | None:
    lon = row.get("LONGITUDE") or row.get("longitude")
    lat = row.get("LATITUDE") or row.get("latitude")
    if lon not in (None, "") and lat not in (None, ""):
        try:
            return float(lon), float(lat)
        except (TypeError, ValueError):
            pass
    geom = row.get("the_geom") or row.get("THE_GEOM") or ""
    m = POINT_RE.search(str(geom))
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def load_dep_csv(path: Path) -> tuple[list[dict], dict]:
    feats: list[dict] = []
    n_total = 0
    n_in_bbox = 0
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n_total += 1
            ll = _parse_lon_lat(row)
            if ll is None:
                continue
            lon, lat = ll
            if not (
                BOUNDS["xmin"] <= lon <= BOUNDS["xmax"]
                and BOUNDS["ymin"] <= lat <= BOUNDS["ymax"]
            ):
                continue
            n_in_bbox += 1
            unitid = row.get("UNITID") or row.get("unitid") or f"row_{n_total}"
            feats.append(
                {
                    "type": "Feature",
                    "properties": {
                        "node_id": f"dep_{unitid}",
                        "unitid": unitid,
                        "source": "nyc_open_data_catch_basin",
                        "kind": "catch_basin",
                        "synthetic": False,
                        "demo_only": False,
                    },
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                }
            )
    return feats, {"n_csv_rows": n_total, "n_in_metro_bbox": n_in_bbox, "n_features": len(feats)}


def _load_geojson_features(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text()).get("features") or [])
    except (OSError, json.JSONDecodeError):
        return []


def _merge(features: list[dict]) -> list[dict]:
    seen: set[tuple[float, float]] = set()
    out: list[dict] = []
    for f in features:
        lon, lat = f["geometry"]["coordinates"][:2]
        key = (round(float(lon), 6), round(float(lat), 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def main() -> dict:
    INFRA.mkdir(parents=True, exist_ok=True)
    osm_path = INFRA / "osm_drains_metro.geojson"
    csv_path = INFRA / "nycdep_catch_basins_metro.csv"

    dep_meta: dict
    if csv_path.exists() and csv_path.stat().st_size > 1_000_000:
        dep_meta = {
            "cached": True,
            "path": str(csv_path),
            "bytes": csv_path.stat().st_size,
        }
        _log(f"Using cached DEP CSV ({dep_meta['bytes']} bytes)")
    else:
        _log("Downloading DEP catch-basin CSV…")
        dep_meta = _download(DEP_CSV_URL, csv_path)
        dep_meta["cached"] = False
        _log(f"Wrote {csv_path} bytes={dep_meta['bytes']}")

    dep_feats, dep_stats = load_dep_csv(csv_path)
    dep_meta.update(dep_stats)
    dep_meta["ok"] = len(dep_feats) > 0
    # Compact JSON summary (full CSV kept for rebuilds; avoid 15MB JSON duplicate)
    (INFRA / "nycdep_catch_basins_metro.json").write_text(
        json.dumps(
            {
                "source": DEP_CSV_URL,
                "n_features": len(dep_feats),
                "extent": "metro",
                "bounds": BOUNDS,
                "sample": dep_feats[:5],
                "note": "Full rows in nycdep_catch_basins_metro.csv; GeoJSON merge in osm_drains_metro.geojson",
            },
            indent=2,
        )
    )
    _log(f"DEP features in metro bbox: {len(dep_feats)}")

    queens_feats = _load_geojson_features(INFRA / "osm_drains_south_queens.geojson")
    prior_metro = _load_geojson_features(osm_path)
    # Keep any prior OSM-tagged points when re-merging
    osm_only = [
        f
        for f in prior_metro
        if str((f.get("properties") or {}).get("source") or "").startswith("osm")
    ]
    if not osm_only:
        osm_only = [
            f
            for f in queens_feats
            if str((f.get("properties") or {}).get("source") or "").startswith("osm")
        ]

    merged = _merge(dep_feats + osm_only)
    fc = {"type": "FeatureCollection", "features": merged}
    osm_path.write_text(json.dumps(fc))
    _log(f"Wrote {osm_path} n={len(merged)}")

    report = {
        "product": "metro_drain_inventory",
        "phase": "C",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "extent": "metro",
        "bounds": BOUNDS,
        "n_features_merged": len(merged),
        "n_dep": len(dep_feats),
        "n_osm": len(osm_only),
        "path": str(osm_path),
        "dep_csv": dep_meta,
        "honesty": (
            "Open catch-basin inventory densified metro-wide from NYC Open Data CSV "
            "(+ OSM inlet/manhole points when present). NOT a DEP sewer model / NOT SWMM. "
            "Capacity proxy still falls back to NLCD base where drain density is zero."
        ),
    }
    (INFRA / "osm_drains_metro_fetch_meta.json").write_text(json.dumps(report, indent=2))
    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "osm_drains_metro_fetch_meta.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {"n_merged": len(merged), "dep_ok": dep_meta.get("ok"), "n_dep": len(dep_feats)},
            indent=2,
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    main()
