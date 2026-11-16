"""P2.7 live MRMS path status vs fixture honesty."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "figures" / "product_assets"


def test_live_mrms_status_labels_fixtures():
    path = ASSETS / "live_mrms_status.json"
    assert path.exists(), "run scripts/build_live_mrms_path.py"
    status = json.loads(path.read_text())
    assert status.get("official_nws") is False
    fixtures = status.get("fixtures") or {}
    assert fixtures.get("ida", {}).get("live") is False
    assert fixtures.get("henri", {}).get("live") is False
    live = status.get("live_fetch") or {}
    assert "status" in live
    assert "reachable" in live
    # Either live ok or documented miss — both honest
    assert live["status"] in ("ok", "no_hour_found")


def test_manifest_live_mrms_block():
    m = json.loads((ASSETS / "product_manifest.json").read_text())
    live = m.get("live_mrms") or {}
    assert live.get("default_ux") == "ida_fixture_replay"
    assert "live_mrms_status.json" in str(live.get("status_json") or "")
    html = (ROOT / "figures" / "product_map.html").read_text()
    assert "liveMrmsNote" in html
    assert (ROOT / "docs" / "live-mrms-qpf-path.md").exists()
