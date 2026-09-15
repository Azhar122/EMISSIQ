"""Plant-frame geometry helpers shared by attribution and quantification.

Coordinates are metres in a local frame: +x east, +y north. Wind direction
follows the meteorological convention — the direction the wind blows FROM.
"""

from __future__ import annotations

import math


def distance_m(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def bearing_deg(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """Compass bearing (0 = north, clockwise) from one point to another."""
    dx, dy = to_x - from_x, to_y - from_y
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def angle_difference_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, 0..180."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def downwind_bearing(wind_dir_from_deg: float) -> float:
    """Direction the plume travels, given the direction the wind comes from."""
    return (wind_dir_from_deg + 180.0) % 360.0


def crosswind_offset_m(
    src_x: float,
    src_y: float,
    rec_x: float,
    rec_y: float,
    wind_dir_from_deg: float,
) -> tuple[float, float]:
    """Split the source→receptor vector into (downwind, |crosswind|) metres.

    A receptor upwind of the source gets a negative downwind distance, which the
    dispersion model treats as "cannot be reached by this plume".
    """
    plume = math.radians(downwind_bearing(wind_dir_from_deg))
    ux, uy = math.sin(plume), math.cos(plume)  # unit vector along the plume
    dx, dy = rec_x - src_x, rec_y - src_y
    downwind = dx * ux + dy * uy
    crosswind = abs(-dx * uy + dy * ux)
    return downwind, crosswind
