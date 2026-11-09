#!/usr/bin/env python3
"""Build the upgraded product map (Tracks 1–3 + validation panel)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from nyc_flash_flood_case_study.config import FIGURES_DIR, PROJECT_ROOT
from nyc_flash_flood_case_study.validation_product import build_validation_product

ASSETS = FIGURES_DIR / "product_assets"
IDA_ASSETS = FIGURES_DIR / "ida_v0_assets"


def _stage_assets() -> dict:
    ASSETS.mkdir(parents=True, exist_ok=True)
    # Only stage vector/infra assets from Ida v0 — never overwrite citywide precip/pluvial rasters.
    keep_prefixes = (
        "precip_",
        "mrms_",
        "diff_",
        "pluvial_",
        "built_surface",
        "ensemble_",
        "fema_",
        "nwm_",
        "drainage_",
        "layer_bounds",
        "product_manifest",
    )
    if IDA_ASSETS.exists():
        for path in IDA_ASSETS.iterdir():
            if not path.is_file():
                continue
            if path.name == "manifest.json":
                continue
            if any(path.name.startswith(p) for p in keep_prefixes):
                dest = ASSETS / path.name
                if dest.exists():
                    continue
            shutil.copy2(path, ASSETS / path.name)
    manifest = json.loads((ASSETS / "manifest.json").read_text()) if (ASSETS / "manifest.json").exists() else {}
    return manifest


def write_product_html(manifest: dict, pluvial: dict, validation: dict) -> Path:
    from product_map_html import write_product_html as _write

    return _write(manifest, pluvial, validation)


def main() -> None:
    print("Staging vector/infra assets…")
    _stage_assets()

    # Earth2-only denser radar stack + time-varying susceptibility (no MRMS).
    print("Building Earth2 radar stack…")
    import importlib.util

    stack_path = Path(__file__).resolve().parent / "build_earth2_radar_stack.py"
    spec = importlib.util.spec_from_file_location("build_earth2_radar_stack", stack_path)
    stack_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(stack_mod)
    stack_mod.main()

    manifest = json.loads((ASSETS / "manifest.json").read_text())
    manifest["product_policy"] = "earth2_only"
    manifest["mrms_qpe"] = None
    manifest["compare_mode"] = False

    ens_meta_path = ASSETS / "ensemble_meta.json"
    if ens_meta_path.exists():
        manifest["ensemble"] = json.loads(ens_meta_path.read_text())
    else:
        manifest["ensemble"] = {
            "available": False,
            "n_members": 1,
            "note": "Single-member deterministic run.",
        }

    pluvial = json.loads((ASSETS / "pluvial_meta.json").read_text())

    print("Building Earth2-only validation product…")
    e2_tif = PROJECT_ROOT / "data" / "processed" / "earth2_precip" / "precip_storm_total.tif"
    # Deliberately omit MRMS — product policy is Earth2-only.
    validation = build_validation_product(e2_tif, None, ASSETS, include_mrms=False)
    validation["product_policy"] = "earth2_only"
    validation["mrms_excluded"] = True

    drain_meta = ASSETS / "drainage_demo_meta.json"
    manifest["swmm"] = {
        "integrated": False,
        "missing": "Calibrated NYC sewer/drainage INP — not available.",
        "demo_drainage": json.loads(drain_meta.read_text()) if drain_meta.exists() else None,
        "note": "Synthetic/open drainage sketch only.",
    }
    manifest["downscaling_hooks"] = {
        "stormcast": "Skipped — natten unavailable (see outputs/stormcast_corrdiff_attempt.json).",
        "corrdiff": "Skipped — natten unavailable.",
        "policy": "Earth2-only; no fake downscaling; nearest-neighbor ~0.25° cells.",
    }

    (ASSETS / "product_manifest.json").write_text(json.dumps(manifest, indent=2))
    html = write_product_html(manifest, pluvial, validation)
    print(f"Wrote {html}")

    try:
        mask_path = Path(__file__).resolve().parent / "apply_land_mask.py"
        spec = importlib.util.spec_from_file_location("apply_land_mask", mask_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        print("Applying coastline land mask…")
        mod.main()
    except Exception as exc:  # noqa: BLE001
        print(f"  land-mask step skipped: {exc}")


if __name__ == "__main__":
    main()
