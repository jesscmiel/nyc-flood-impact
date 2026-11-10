"""Spike notes / probes for SFINCS and LISFLOOD-FP (open stack only).

Neither engine is runnable end-to-end in this environment today:
- LISFLOOD-FP: no pip package; needs a compiled binary.
- SFINCS: ``hydromt-sfincs`` builds model schemas but the SFINCS executable
  is not shipped on PyPI / latest GitHub release assets for Linux.

Fallback: improved pysheds HAND/bathtub borough spike (see pysheds_borough).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from importlib import util
from pathlib import Path
from typing import Any


@dataclass
class EngineProbe:
    name: str
    installable: bool
    runnable: bool
    detail: str


def probe_engines() -> list[EngineProbe]:
    probes: list[EngineProbe] = []

    # LISFLOOD-FP
    exe = shutil.which("lisflood") or shutil.which("lisflood.exe")
    probes.append(
        EngineProbe(
            name="LISFLOOD-FP",
            installable=False,
            runnable=bool(exe),
            detail=(
                f"binary found at {exe}"
                if exe
                else "No pip package; no lisflood binary on PATH. Needs compiled LISFLOOD-FP."
            ),
        )
    )

    # hydromt-sfincs (schema only)
    hydromt_ok = util.find_spec("hydromt_sfincs") is not None
    sfincs_bin = shutil.which("sfincs")
    detail = "hydromt-sfincs not installed"
    if hydromt_ok:
        detail = (
            "hydromt-sfincs importable (model builder). "
            + (
                f"sfincs binary at {sfincs_bin}"
                if sfincs_bin
                else "No sfincs executable on PATH / release assets — cannot run simulation."
            )
        )
    probes.append(
        EngineProbe(
            name="SFINCS",
            installable=hydromt_ok,
            runnable=bool(sfincs_bin),
            detail=detail,
        )
    )

    # pysheds always preferred fallback
    pysheds_ok = util.find_spec("pysheds") is not None
    probes.append(
        EngineProbe(
            name="pysheds",
            installable=pysheds_ok,
            runnable=pysheds_ok,
            detail="HAND + bathtub research inundation (fallback / MVP engine).",
        )
    )
    return probes


def try_build_sfincs_schema(out_dir: Path, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    """Build a minimal SFINCS model directory with hydromt if available (no run)."""
    out: dict[str, Any] = {"attempted": True, "wrote": False, "path": str(out_dir)}
    if util.find_spec("hydromt_sfincs") is None:
        out["error"] = "hydromt_sfincs not installed"
        return out
    try:
        from hydromt_sfincs import SfincsModel

        out_dir.mkdir(parents=True, exist_ok=True)
        # Empty region setup — documents the schema path without claiming a run.
        model = SfincsModel(root=str(out_dir), mode="w+")
        # region as xmin, ymin, xmax, ymax
        model.setup_grid_from_region(region={"bbox": list(bbox)}, res=50)
        model.write()
        out["wrote"] = True
        out["note"] = (
            "Schema written only — SFINCS binary missing; not a completed inundation run."
        )
    except Exception as exc:  # noqa: BLE001 — spike must record any blocker
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def write_spike_report(path: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    report = {
        "product": "flood_risk_research_prototype",
        "enterprise": False,
        "hens": False,
        "probes": [asdict(p) for p in probe_engines()],
        "conclusion": (
            "SFINCS/LISFLOOD-FP blocked without native binaries. "
            "MVP inundation remains improved pysheds HAND/bathtub."
        ),
    }
    if extra:
        report.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    from nyc_flash_flood_case_study.config import OUTPUTS_DIR, PROJECT_ROOT
    from nyc_flash_flood_case_study.extents import EXTENTS

    b = EXTENTS["south_queens"]["bounds"]
    bbox = (b["xmin"], b["ymin"], b["xmax"], b["ymax"])
    schema = try_build_sfincs_schema(PROJECT_ROOT / "outputs" / "sfincs_spike_queens", bbox)
    report = write_spike_report(OUTPUTS_DIR / "inundation_engine_spike.json", {"sfincs_schema": schema})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
