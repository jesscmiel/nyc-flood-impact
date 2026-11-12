"""Inundation engines: pysheds HAND/bathtub first; SFINCS Advanced research track.

Also exposes an open drainage capacity proxy (NLCD + mm/hr sink) — not a DEP sewer /
not SWMM. Metro nested SFINCS is Advanced-only; HAND remains primary product depth.
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
from flood_risk.inundation.sfincs_nested import (  # noqa: F401
    ENGINE_ID as SFINCS_NESTED_ENGINE_ID,
    ENGINE_LABEL as SFINCS_NESTED_LABEL,
)
