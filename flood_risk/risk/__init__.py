"""Risk metrics: scenario depth × exposure; return-period placeholders (not calibrated)."""

from flood_risk.risk.depth_asset_tables import DEPTH_BANDS, summarize_assets
from flood_risk.risk.return_period import build_rp_placeholders

__all__ = ["DEPTH_BANDS", "summarize_assets", "build_rp_placeholders"]
