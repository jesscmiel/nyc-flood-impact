#!/usr/bin/env python3
"""P2.5 — denser open drain inventory for the capacity proxy (not SWMM / not DEP sewer).

- Refresh/merge NYC Open Data catch-basin CSV (+ cached OSM points)
- Rebuild drain-density with a slightly wider open-data influence buffer
- Export a denser product sample for the Decision Desk map
- Update drainage_capacity_meta honesty + coverage stats

Does NOT invent basins. Does NOT rebuild SWMM. HAND remains primary.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from flood_risk.inundation.drainage_capacity import (  # noqa: E402
    DRAIN_BUFFER_DEG,
    capacity_mm_hr,
    drain_coverage_fraction,
    drain_density_norm,
    effective_sink_mm,
    load_drain_points,
    load_impervious_fraction,
    default_drain_candidate_paths,
)
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    RAW_DIR,
)
from nyc_flash_flood_case_study.extents import EXTENTS, PRIMARY_DATA_EXTENT  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INFRA = RAW_DIR / "infrastructure"
DRAIN_DIR = PROCESSED_DIR / "drainage_capacity"
# ~220 m influence (was ~150 m) — densifies *coverage credit* from open inventory only
DENSE_BUFFER_DEG = 0.0022
PRODUCT_SAMPLE_N = 5000


def _refresh_open_inventory() -> dict:
    from fetch_osm_drains_metro import main as fetch_main

    return fetch_main()


def _land_mask(shape, transform) -> np.ndarray:
    mask_p = PROCESSED_DIR / "land_mask_metro.tif"
    if not mask_p.exists():
        return np.ones(shape, dtype=bool)
    with rasterio.open(mask_p) as ms:
        data = ms.read(1)
        if data.shape == shape:
            return data > 0
    return np.ones(shape, dtype=bool)


def _write_tif(path: Path, data: np.ndarray, transform, crs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        compress="deflate",
        nodata=np.nan,
    ) as dst:
        dst.write(data.astype(np.float32), 1)


def _product_sample(geojson_path: Path, n: int = PRODUCT_SAMPLE_N) -> dict:
    feats = json.loads(geojson_path.read_text()).get("features") or []
    if len(feats) <= n:
        sample = feats
    else:
        # Stratified-ish: take every k-th after a fixed stride for spatial spread
        step = max(1, len(feats) // n)
        sample = feats[::step][:n]
    return {
        "type": "FeatureCollection",
        "features": sample,
        "honesty": (
            f"Product sample of {len(sample)} / {len(feats)} open catch-basin points — "
            "NOT a DEP sewer model / NOT SWMM."
        ),
        "n_full": len(feats),
        "n_sample": len(sample),
    }


def main() -> dict:
    print("Refreshing open catch-basin inventory…")
    fetch_report = _refresh_open_inventory()

    dem = RAW_DIR / "terrain" / "dem_usgs_metro_work30m.tif"
    if not dem.exists():
        dem = RAW_DIR / "terrain" / "dem_usgs_metro.tif"
    rain = PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif"
    nlcd = RAW_DIR / "landcover" / "nlcd_2021_impervious_citywide.tif"
    if not dem.exists() or not rain.exists() or not nlcd.exists():
        raise SystemExit(f"missing dem/rain/nlcd: {dem.exists()} {rain.exists()} {nlcd.exists()}")

    pts, dpath, status = load_drain_points(
        default_drain_candidate_paths(INFRA, ASSETS, FIGURES_DIR / "ida_v0_assets", RAW_DIR)
    )
    print(f"Loaded drain points n={len(pts)} status={status} path={dpath}")

    with rasterio.open(dem) as dem_ds, rasterio.open(rain) as rain_ds:
        shape = (dem_ds.height, dem_ds.width)
        transform, crs = dem_ds.transform, dem_ds.crs
        precip = rain_ds.read(1).astype(np.float32)

    land = _land_mask(shape, transform)
    impervious = load_impervious_fraction(shape, transform, crs, nlcd)
    drain_norm = drain_density_norm(shape, transform, pts, buffer_deg=DENSE_BUFFER_DEG)
    coverage = drain_coverage_fraction(drain_norm, land)
    # Compare legacy buffer for honesty delta
    legacy = drain_density_norm(shape, transform, pts, buffer_deg=DRAIN_BUFFER_DEG)
    legacy_cov = drain_coverage_fraction(legacy, land)

    capacity = capacity_mm_hr(impervious, drain_norm)
    sink, excess, efficiency = effective_sink_mm(precip, capacity)

    DRAIN_DIR.mkdir(parents=True, exist_ok=True)
    _write_tif(DRAIN_DIR / "drain_density_norm_metro.tif", drain_norm, transform, crs)
    _write_tif(DRAIN_DIR / "drainage_capacity_mm_hr.tif", capacity, transform, crs)
    _write_tif(DRAIN_DIR / "drainage_sink_mm.tif", sink, transform, crs)
    _write_tif(DRAIN_DIR / "excess_precip_mm.tif", excess, transform, crs)
    _write_tif(DRAIN_DIR / "drainage_efficiency.tif", efficiency, transform, crs)
    _write_tif(DRAIN_DIR / "impervious_fraction_metro.tif", impervious, transform, crs)

    sample_fc = _product_sample(INFRA / "osm_drains_metro.geojson")
    # Keep legacy sample name + denser alias
    (ASSETS / "dep_catch_basins_sample.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": sample_fc["features"]})
    )
    (ASSETS / "dep_catch_basins_dense_sample.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": sample_fc["features"]})
    )

    meta = {
        "product": "drainage_capacity_proxy",
        "engine": "drainage_capacity_proxy_v1",
        "extent": PRIMARY_DATA_EXTENT,
        "shape": list(shape),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "p25_denser_inventory": True,
        "drain_buffer_deg": DENSE_BUFFER_DEG,
        "drain_buffer_deg_legacy": DRAIN_BUFFER_DEG,
        "drain_points": {
            "n": len(pts),
            "status": status,
            "path": str(dpath) if dpath else None,
            "coverage": coverage,
            "coverage_legacy_buffer": legacy_cov,
            "fetch": {
                "n_features_merged": fetch_report.get("n_features_merged"),
                "n_dep": fetch_report.get("n_dep"),
                "n_osm": fetch_report.get("n_osm"),
            },
            "note": (
                "Open NYC catch-basin inventory (CSV) + OSM inlet/manhole points. "
                "P2.5 widens influence buffer for coverage densification; does not invent basins."
            ),
        },
        "product_sample": {
            "geojson": "dep_catch_basins_dense_sample.geojson",
            "legacy_alias": "dep_catch_basins_sample.geojson",
            "n_sample": sample_fc["n_sample"],
            "n_full": sample_fc["n_full"],
        },
        "not_dep_sewer": True,
        "not_swmm": True,
        "official_nws": False,
        "decision_grade": False,
        "honesty": (
            "Denser open catch-basin inventory for capacity proxy screening — "
            "NOT DEP sewer ops / NOT SWMM / NOT official closures."
        ),
        "stats_on_land": {
            "coverage_fraction": coverage["fraction_with_drain_credit"],
            "coverage_fraction_legacy": legacy_cov["fraction_with_drain_credit"],
            "capacity_mm_hr_mean": float(np.nanmean(np.where(land, capacity, np.nan))),
            "excess_mm_mean": float(np.nanmean(np.where(land, excess, np.nan))),
        },
    }
    (DRAIN_DIR / "drainage_capacity_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "drainage_capacity_meta.json").write_text(json.dumps(meta, indent=2))
    (ASSETS / "denser_drain_inventory_meta.json").write_text(json.dumps(meta, indent=2))
    (OUTPUTS_DIR / "denser_drain_inventory_meta.json").write_text(json.dumps(meta, indent=2))

    for name in ("product_manifest.json", "manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        m["drainage_capacity_proxy"] = {
            "meta": "drainage_capacity_meta.json",
            "dense_sample_geojson": "dep_catch_basins_dense_sample.geojson",
            "n_open_points": len(pts),
            "coverage_fraction": coverage["fraction_with_drain_credit"],
            "buffer_deg": DENSE_BUFFER_DEG,
            "not_swmm": True,
            "not_dep_sewer": True,
            "honesty": meta["honesty"],
        }
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
        write_product_html(manifest, pluvial, validation)
    except Exception as exc:  # noqa: BLE001
        print(f"html regen skipped: {exc}")

    summary = {
        "n_points": len(pts),
        "coverage_fraction": coverage["fraction_with_drain_credit"],
        "coverage_legacy": legacy_cov["fraction_with_drain_credit"],
        "sample_n": sample_fc["n_sample"],
        "buffer_deg": DENSE_BUFFER_DEG,
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
