#!/usr/bin/env python3
"""Build + Docker-run metro nested SFINCS (Advanced research hydro).

Layers:
  1) Metro coarse (~100 m) — continuous domain, spatial MRMS + drainage sink
  2) South Queens nest (~50 m) — same shared sink forcing
  3) Composite PNG/TIF for the Advanced product toggle

HAND/bathtub remains the only primary depth. No SWMM / no fake DEP pipes.
No Earth2Studio Enterprise / HENS. Research only — NOT official NWS.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from flood_risk.inundation.sfincs_nested import (  # noqa: E402
    ENGINE_ID,
    ENGINE_LABEL,
    IMAGE,
    METRO_RES_M,
    NEST_RES_M,
    build_sfincs_model,
    composite_nest_onto_coarse,
    export_depth_from_map_nc,
    run_sfincs_docker,
)
from nyc_flash_flood_case_study.config import (  # noqa: E402
    FIGURES_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
)
from nyc_flash_flood_case_study.extents import EXTENTS  # noqa: E402

ASSETS = FIGURES_DIR / "product_assets"
INUN = PROCESSED_DIR / "inundation"
METRO_MODEL = OUTPUTS_DIR / "sfincs_metro_ida"
NEST_MODEL = OUTPUTS_DIR / "sfincs_queens_ida"

DEM_CANDIDATES = [
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro.tif",
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_metro_work30m.tif",
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_1_3_arcsec.tif",
    PROJECT_ROOT / "data" / "raw" / "terrain" / "dem_usgs_citywide.tif",
]
RAIN_CANDIDATES = [
    PROCESSED_DIR / "mrms_qpe_metro" / "mrms_qpe_metro_storm_total.tif",
    PROCESSED_DIR / "earth2_precip" / "mrms_qpe_ida_precip_storm_total.tif",
    PROCESSED_DIR / "mrms_qpe" / "mrms_qpe_storm_total.tif",
]


def _first_existing(paths: list[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"None of {paths} exist")


def wire_manifest(composite_meta: dict, metro_meta: dict, nest_meta: dict) -> None:
    for name in ("manifest.json", "product_manifest.json"):
        mp = ASSETS / name
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        b = EXTENTS["metro"]["bounds"]
        leaflet = [[b["ymin"], b["xmin"]], [b["ymax"], b["xmax"]]]
        m["inundation_sfincs_nested"] = {
            "png": composite_meta["png"],
            "meta": "depth_sfincs_metro_nested_ida_meta.json",
            "engine": ENGINE_ID,
            "engine_label": ENGINE_LABEL,
            "extent": "metro",
            "nest_extent": "south_queens",
            "bounds": leaflet,
            "role": "advanced_research_hydro",
            "primary": False,
            "not_swmm": True,
            "compare_with": "inundation_citywide",
            "honesty": composite_meta.get("honesty"),
            "metro_res_m": METRO_RES_M,
            "nest_res_m": NEST_RES_M,
            "metro_png": metro_meta.get("png"),
            "nest_png": nest_meta.get("png"),
        }
        # Keep Queens spike entry for the fine-nest-only toggle.
        if (ASSETS / "depth_sfincs_queens_ida_m.png").exists():
            m["inundation_sfincs"] = {
                "png": "depth_sfincs_queens_ida_m.png",
                "meta": "depth_sfincs_queens_ida_meta.json",
                "engine": nest_meta.get("engine", "sfincs_docker"),
                "extent": "south_queens",
                "role": "advanced_research_hydro_nest",
                "primary": False,
                "parent": "inundation_sfincs_nested",
                "honesty": nest_meta.get("honesty")
                or "Queens nest only — part of Advanced nested SFINCS; not peer with HAND.",
            }
        engines = m.get("depth_engines") or {}
        engines["primary"] = engines.get("primary") or {
            "id": "pysheds_hand_bathtub_v2",
            "extent": "metro",
            "use_for": "Default Asset Decision Desk ranking (primary depth)",
        }
        engines["alternate"] = {
            "id": ENGINE_ID,
            "extent": "metro + south_queens nest",
            "forcing": "spatial MRMS precip grid + drainage_capacity_proxy_v1 sink",
            "use_for": "Advanced research hydro only — magnitudes not peer-comparable to HAND",
            "honesty": (
                "Metro nested SFINCS is Advanced research hydro. HAND stays primary. "
                "No SWMM / no fake DEP network. NOT NWS / NOT decision-grade."
            ),
            "not_swmm": True,
            "primary": False,
        }
        m["depth_engines"] = engines
        desk = m.get("asset_decision_desk") or {}
        desk["sfincs_role"] = "advanced_research_hydro"
        desk["primary_depth_engine"] = desk.get(
            "primary_depth_engine", "pysheds_hand_bathtub_v2"
        )
        desk["not_swmm"] = True
        m["asset_decision_desk"] = desk
        m["advanced_research_hydro"] = {
            "id": ENGINE_ID,
            "label": ENGINE_LABEL,
            "png": composite_meta["png"],
            "meta": "depth_sfincs_metro_nested_ida_meta.json",
            "docker_image": IMAGE,
            "shared_sink": True,
            "not_swmm": True,
            "primary_remains": "pysheds_hand_bathtub_v2",
        }
        mp.write_text(json.dumps(m, indent=2))


def write_repo_doc(summary: dict) -> None:
    docs = PROJECT_ROOT / "docs" / "metro-nested-sfincs.md"
    metro = summary.get("metro_depth") or {}
    nest = summary.get("nest_depth") or {}
    comp = summary.get("composite") or {}
    precip = (summary.get("metro_build") or {}).get("precip_netcdf") or {}
    drain = precip.get("drainage_capacity_proxy") or {}
    docs.write_text(
        f"""# Metro nested SFINCS — Advanced research hydro

**HAND stays primary.** SFINCS is an Advanced research hydro track only.  
**No SWMM** / no fake DEP pipe network. Open drainage sink = `drainage_capacity_proxy_v1`.  
No Enterprise / HENS. Research only — NOT official NWS / NOT decision-grade.

## What shipped

| Layer | Domain | Grid | Role |
| --- | --- | --- | --- |
| Metro coarse | `EXTENTS["metro"]` | ~{METRO_RES_M} m | Continuous Advanced hydro |
| Queens nest | `EXTENTS["south_queens"]` | ~{NEST_RES_M} m | Fine nest over South Queens / Jamaica Bay |
| Composite | metro grid + nest paste | — | Product Advanced toggle |

Shared forcing: **spatial** MRMS Ida storm-total → mm/hr rate field (`setup_precip_forcing_from_grid`, `aggregate=False`) minus open drainage capacity proxy. Uniform domain-mean forcing is forbidden.

## Docker

```bash
sg docker -c 'docker pull {IMAGE}'

# Metro coarse
sg docker -c 'docker run --rm -v {METRO_MODEL.resolve()}:/data {IMAGE}'

# Queens nest
sg docker -c 'docker run --rm -v {NEST_MODEL.resolve()}:/data {IMAGE}'
```

One-shot:

```bash
.venv/bin/python scripts/build_and_run_sfincs_metro_nested.py
# reuse existing Queens nest NetCDF if fresh rebuild not needed:
.venv/bin/python scripts/build_and_run_sfincs_metro_nested.py --reuse-nest
```

## Artifacts

| Artifact | Path |
| --- | --- |
| Metro depth TIF | `data/processed/inundation/depth_sfincs_metro_ida_m.tif` |
| Nest depth TIF | `data/processed/inundation/depth_sfincs_queens_ida_m.tif` |
| Composite TIF | `data/processed/inundation/depth_sfincs_metro_nested_ida_m.tif` |
| Composite PNG | `figures/product_assets/depth_sfincs_metro_nested_ida_m.png` |
| Meta | `figures/product_assets/depth_sfincs_metro_nested_ida_meta.json` |
| Docker cmds | `outputs/sfincs_metro_nested_docker_commands.txt` |

## Run stats (this machine)

| Metric | Metro coarse | Queens nest | Composite |
| --- | ---: | ---: | ---: |
| max depth (m) | {metro.get("max_m")} | {nest.get("max_m")} | {comp.get("max_m")} |
| wet fraction (>5 mm) | {metro.get("wet_fraction")} | {nest.get("wet_fraction")} | {comp.get("wet_fraction")} |

Precip (shared sink): mean rate ≈ **{precip.get("mean_rate_mm_hr")}** mm/hr · max ≈ **{precip.get("max_rate_mm_hr")}** · drain points n≈**{drain.get("drain_points_n")}** · sink applied={drain.get("applied")}.

## Product wiring

- Primary depth toggle = metro HAND × MRMS after drainage proxy (unchanged).
- Advanced · research hydro → **Metro nested SFINCS** (`lySfincsNested`) + optional Queens-nest-only (`lySfincs`).
- Manifest keys: `inundation_sfincs_nested`, `advanced_research_hydro`, `depth_engines.alternate`.

## Honesty

- Magnitudes are **not** peer-comparable to cm-scale HAND screening.
- Drainage sink ≠ DEP sewer performance ≠ SWMM.
- Nested composite pastes the Queens fine nest onto the metro coarse field for visualization — not a two-way coupled nest exchange.
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reuse-nest",
        action="store_true",
        help="Reuse existing Queens nest model/output if sfincs_map.nc present",
    )
    ap.add_argument(
        "--skip-metro-docker",
        action="store_true",
        help="Skip metro Docker if sfincs_map.nc already present",
    )
    args = ap.parse_args()

    dem = _first_existing(DEM_CANDIDATES)
    rain = _first_existing(RAIN_CANDIDATES)
    metro_bounds = EXTENTS["metro"]["bounds"]
    nest_bounds = EXTENTS["south_queens"]["bounds"]
    ASSETS.mkdir(parents=True, exist_ok=True)
    INUN.mkdir(parents=True, exist_ok=True)

    metro_map = METRO_MODEL / "sfincs_map.nc"
    reuse_metro = args.skip_metro_docker and metro_map.exists()
    if reuse_metro:
        print("Reusing existing metro coarse model + sfincs_map.nc")
        metro_build = (
            json.loads((METRO_MODEL / "build_meta.json").read_text())
            if (METRO_MODEL / "build_meta.json").exists()
            else {"precip_netcdf": {}}
        )
        metro_log = {"run_returncode": 0, "skipped": True}
    else:
        print("Building metro coarse SFINCS…")
        metro_build = build_sfincs_model(
            model_dir=METRO_MODEL,
            dem=dem,
            rain_tif=rain,
            extent_bounds=metro_bounds,
            res_m=METRO_RES_M,
            label="metro_coarse",
            apply_drainage_proxy=True,
            root=PROJECT_ROOT,
        )
        print(json.dumps({"metro_res_m": METRO_RES_M, "precip": metro_build["precip_netcdf"]}, indent=2))
        print("Running metro SFINCS via Docker…")
        metro_log = run_sfincs_docker(
            METRO_MODEL,
            log_path=OUTPUTS_DIR / "sfincs_metro_docker_log.json",
            commands_path=OUTPUTS_DIR / "sfincs_metro_docker_commands.txt",
        )

    metro_depth = export_depth_from_map_nc(
        METRO_MODEL,
        out_tif=INUN / "depth_sfincs_metro_ida_m.tif",
        out_png=ASSETS / "depth_sfincs_metro_ida_m.png",
        out_meta=ASSETS / "depth_sfincs_metro_ida_meta.json",
        extent_bounds=metro_bounds,
        # Native ~0.001° display grid (~SFINCS 100 m) — avoid HAND 30 m grid bloat.
        ref_tif=None,
        label="metro_coarse",
    )
    shutil.copy(ASSETS / "depth_sfincs_metro_ida_meta.json", INUN / "depth_sfincs_metro_ida_meta.json")

    nest_map = NEST_MODEL / "sfincs_map.nc"
    nest_tif = INUN / "depth_sfincs_queens_ida_m.tif"
    if args.reuse_nest and nest_map.exists() and nest_tif.exists():
        print("Reusing existing Queens nest outputs")
        nest_build = json.loads((NEST_MODEL / "build_meta.json").read_text()) if (NEST_MODEL / "build_meta.json").exists() else {}
        nest_log = {"run_returncode": 0, "skipped": True, "reused": True}
        nest_depth = (
            json.loads((ASSETS / "depth_sfincs_queens_ida_meta.json").read_text())
            if (ASSETS / "depth_sfincs_queens_ida_meta.json").exists()
            else {"png": "depth_sfincs_queens_ida_m.png", "tif": str(nest_tif)}
        )
    else:
        print("Building Queens nest SFINCS (shared sink)…")
        nest_build = build_sfincs_model(
            model_dir=NEST_MODEL,
            dem=dem,
            rain_tif=rain,
            extent_bounds=nest_bounds,
            res_m=NEST_RES_M,
            label="south_queens_nest",
            apply_drainage_proxy=True,
            root=PROJECT_ROOT,
        )
        print("Running Queens nest via Docker…")
        nest_log = run_sfincs_docker(
            NEST_MODEL,
            log_path=OUTPUTS_DIR / "sfincs_queens_docker_log.json",
            commands_path=OUTPUTS_DIR / "sfincs_queens_docker_commands.txt",
        )
        nest_depth = export_depth_from_map_nc(
            NEST_MODEL,
            out_tif=nest_tif,
            out_png=ASSETS / "depth_sfincs_queens_ida_m.png",
            out_meta=ASSETS / "depth_sfincs_queens_ida_meta.json",
            extent_bounds=nest_bounds,
            ref_tif=INUN / "depth_south_queens_mrms_qpe_ida_storm_total_m.tif",
            label="south_queens_nest",
        )
        shutil.copy(
            ASSETS / "depth_sfincs_queens_ida_meta.json",
            INUN / "depth_sfincs_queens_ida_meta.json",
        )

    print("Compositing nest onto metro…")
    composite = composite_nest_onto_coarse(
        INUN / "depth_sfincs_metro_ida_m.tif",
        nest_tif,
        out_tif=INUN / "depth_sfincs_metro_nested_ida_m.tif",
        out_png=ASSETS / "depth_sfincs_metro_nested_ida_m.png",
        out_meta=ASSETS / "depth_sfincs_metro_nested_ida_meta.json",
    )
    shutil.copy(
        ASSETS / "depth_sfincs_metro_nested_ida_meta.json",
        INUN / "depth_sfincs_metro_nested_ida_meta.json",
    )

    # Combined commands file for docs / assets
    cmds = []
    for p in (
        OUTPUTS_DIR / "sfincs_metro_docker_commands.txt",
        OUTPUTS_DIR / "sfincs_queens_docker_commands.txt",
    ):
        if p.exists():
            cmds.append(p.read_text().strip())
    combined = OUTPUTS_DIR / "sfincs_metro_nested_docker_commands.txt"
    combined.write_text("\n\n".join(cmds) + "\n")
    shutil.copy(combined, ASSETS / "sfincs_metro_nested_docker_commands.txt")

    wire_manifest(composite, metro_depth, nest_depth)
    summary = {
        "engine": ENGINE_ID,
        "metro_build": metro_build,
        "nest_build": nest_build if isinstance(nest_build, dict) else {},
        "metro_log_rc": metro_log.get("run_returncode"),
        "nest_log_rc": nest_log.get("run_returncode"),
        "metro_depth": metro_depth,
        "nest_depth": nest_depth,
        "composite": composite,
        "primary_remains": "pysheds_hand_bathtub_v2",
        "not_swmm": True,
    }
    (OUTPUTS_DIR / "sfincs_metro_nested_summary.json").write_text(json.dumps(summary, indent=2))
    (ASSETS / "sfincs_metro_nested_summary.json").write_text(json.dumps(summary, indent=2))
    write_repo_doc(summary)

    # Sync product HTML so the Advanced toggle is live
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
        print(json.dumps({"composite": composite, "html": str(html_path)}, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"composite": composite, "html_refresh_warning": str(exc)}, indent=2))


if __name__ == "__main__":
    main()
