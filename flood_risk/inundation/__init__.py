"""Inundation engines: pysheds HAND/bathtub first; SFINCS/LISFLOOD-FP candidates.

Also exposes an open drainage capacity proxy (NLCD + mm/hr sink) — not a DEP sewer model.
"""

from flood_risk.inundation.drainage_capacity import (  # noqa: F401
    ENGINE_ID as DRAINAGE_PROXY_ID,
    effective_sink_mm,
    param_meta as drainage_param_meta,
)
from flood_risk.inundation.hand_bathtub import (  # noqa: F401
    ENGINE_ID as HAND_ENGINE_ID,
    depth_from_rain,
    param_meta as hand_param_meta,
)
