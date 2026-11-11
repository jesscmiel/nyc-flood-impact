"""Event catalog and map extents for the product UI."""

from __future__ import annotations

EVENTS = {
    "ida-2021": {
        "id": "ida-2021",
        "label": "Hurricane Ida remnants (2021-09-01)",
        "init_time": "2021-09-01T12:00:00",
        "start": "2021-09-01T00:00:00",
        "end": "2021-09-02T23:00:00",
        "default_extent": "citywide",
        "notes": "Primary v0 case study. Flash Flood Emergency for NYC. Earth2 shown as ~0.25° cells over metro NYC.",
        "available": True,
    },
    "placeholder-future": {
        "id": "placeholder-future",
        "label": "Future event (placeholder)",
        "init_time": None,
        "start": None,
        "end": None,
        "default_extent": "citywide",
        "notes": "Hook for additional storms — not loaded yet.",
        "available": False,
    },
}

EXTENTS = {
    # Data-domain rectangle used by existing DEM / MRMS / pysheds rasters (~90 m DEM).
    # Overlays stay georeferenced to these bounds until a continuous-domain rebuild.
    "citywide": {
        "id": "citywide",
        "label": "NYC five-borough data domain",
        "bounds": {"xmin": -74.28, "ymin": 40.48, "xmax": -73.68, "ymax": 40.93},
        "role": "data_domain",
    },
    # Map framing only — larger continuous viewport so the UI is not a tight Queens/box crop.
    # Raster products still cover `citywide` until DEM + forcing are re-fetched for metro.
    "metro": {
        "id": "metro",
        "label": "NYC metro continuous (map frame)",
        "bounds": {"xmin": -74.45, "ymin": 40.40, "xmax": -73.50, "ymax": 41.05},
        "role": "map_frame",
    },
    "south_queens": {
        "id": "south_queens",
        "label": "South Queens / Jamaica Bay (SFINCS spike)",
        "bounds": {"xmin": -74.12, "ymin": 40.55, "xmax": -73.72, "ymax": 40.73},
        "role": "sfincs_spike",
    },
}

# Default map framing prefers continuous metro view over the hard data rectangle.
DEFAULT_MAP_EXTENT = "metro"


def bounds_list(extent_id: str) -> list[list[float]]:
    b = EXTENTS[extent_id]["bounds"]
    return [[b["ymin"], b["xmin"]], [b["ymax"], b["xmax"]]]
