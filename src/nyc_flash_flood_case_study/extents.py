"""Event catalog and map extents for the product UI."""

from __future__ import annotations

EVENTS = {
    "ida-2021": {
        "id": "ida-2021",
        "label": "Hurricane Ida remnants (2021-09-01)",
        "init_time": "2021-09-01T12:00:00",
        "start": "2021-09-01T00:00:00",
        "end": "2021-09-02T23:00:00",
        "default_extent": "metro",
        "notes": "Primary case study. Flash Flood Emergency for NYC. Decision Desk + MRMS awareness.",
        "available": True,
        "desk_key": "ida-2021",
    },
    "henri-2021": {
        "id": "henri-2021",
        "label": "Tropical Storm Henri remnants (2021-08-21)",
        "init_time": "2021-08-21T18:00:00",
        "start": "2021-08-21T18:00:00",
        "end": "2021-08-22T18:00:00",
        "default_extent": "metro",
        "notes": (
            "Second-storm Decision Desk when MRMS×HAND assets are built "
            "(scripts/build_second_storm_desk.py). Research only."
        ),
        "available": False,  # flipped True when second_storm_henri_meta.json says available
        "desk_key": "henri-2021",
    },
    "placeholder-future": {
        "id": "placeholder-future",
        "label": "Future event (placeholder)",
        "init_time": None,
        "start": None,
        "end": None,
        "default_extent": "metro",
        "notes": "Hook for additional storms — not loaded yet.",
        "available": False,
    },
}

EXTENTS = {
    # Legacy five-borough rectangle (pre-rebuild ~90 m DEM / MRMS clips).
    "citywide": {
        "id": "citywide",
        "label": "NYC five-borough (legacy data domain)",
        "bounds": {"xmin": -74.28, "ymin": 40.48, "xmax": -73.68, "ymax": 40.93},
        "role": "legacy_data_domain",
    },
    # Primary data + map domain after metro DEM / MRMS / HAND rebuild.
    "metro": {
        "id": "metro",
        "label": "NYC metro continuous",
        "bounds": {"xmin": -74.45, "ymin": 40.40, "xmax": -73.50, "ymax": 41.05},
        "role": "data_domain_and_map_frame",
    },
    "south_queens": {
        "id": "south_queens",
        "label": "South Queens / Jamaica Bay (SFINCS spike)",
        "bounds": {"xmin": -74.12, "ymin": 40.55, "xmax": -73.72, "ymax": 40.73},
        "role": "sfincs_spike",
    },
}

# Default map framing + primary inundation data domain.
DEFAULT_MAP_EXTENT = "metro"
PRIMARY_DATA_EXTENT = "metro"


def bounds_list(extent_id: str) -> list[list[float]]:
    b = EXTENTS[extent_id]["bounds"]
    return [[b["ymin"], b["xmin"]], [b["ymax"], b["xmax"]]]
