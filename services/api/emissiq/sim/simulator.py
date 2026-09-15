"""Sensor simulator.

Generates normal baseline behaviour plus controlled anomalies. CH4 at each
sensor is produced by the SAME Gaussian plume model that quantification later
inverts, so the demo is internally consistent: the estimator is being asked to
recover a number the simulator actually used.

Everything is seeded. The same scenario replays identically every time.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

from ..engines.geometry import crosswind_offset_m
from ..engines.quantification import ppm_to_kg_m3, sigmas
from . import layout


@dataclass
class Tick:
    """One second of plant state — what a real ingest pipeline would receive."""

    ts: dt.datetime
    facility_id: str
    readings: list[dict]  # one per sensor
    weather: dict
    equipment_states: dict[str, str]
    run_phase: str


def kg_m3_to_ppm(kg_m3: float) -> float:
    return kg_m3 * 1e6 * 24.45 / 16.043


def plume_ppm(
    q_kg_h: float,
    source_xy: tuple[float, float],
    receptor_xy: tuple[float, float],
    wind_speed_ms: float,
    wind_dir_from_deg: float,
    stability: str = "D",
    release_height_m: float = layout.RELEASE_HEIGHT_M,
    receptor_height_m: float = 2.0,
) -> float:
    """Forward Gaussian plume: concentration above background, in ppm."""
    if q_kg_h <= 0:
        return 0.0
    u = max(wind_speed_ms, 0.5)
    downwind, crosswind = crosswind_offset_m(*source_xy, *receptor_xy, wind_dir_from_deg)
    if downwind <= 1.0:
        return 0.0

    sy, sz = sigmas(downwind, stability)
    h, z = release_height_m, receptor_height_m
    lateral = math.exp(-(crosswind**2) / (2 * sy**2))
    vertical = math.exp(-((z - h) ** 2) / (2 * sz**2)) + math.exp(
        -((z + h) ** 2) / (2 * sz**2)
    )
    c_kg_m3 = (q_kg_h / 3600.0) / (2 * math.pi * u * sy * sz) * lateral * vertical
    return kg_m3_to_ppm(c_kg_m3)


def travel_time_s(
    source_xy: tuple[float, float],
    receptor_xy: tuple[float, float],
    wind_speed_ms: float,
    wind_dir_from_deg: float,
) -> float:
    """Advection delay between release and arrival at a receptor."""
    downwind, _ = crosswind_offset_m(*source_xy, *receptor_xy, wind_dir_from_deg)
    if downwind <= 0:
        return float("inf")
    return downwind / max(wind_speed_ms, 0.5)


class SensorSimulator:
    """Emits per-second plant state. A release profile is supplied as a callable
    q(t_seconds) -> kg CH4/h so different scenarios reuse the same physics."""

    def __init__(
        self,
        seed: int = 20260914,
        wind_speed_ms: float = layout.DEMO_WIND_SPEED_MS,
        wind_dir_from_deg: float = layout.DEMO_WIND_DIR_FROM_DEG,
        stability: str = layout.DEMO_STABILITY,
    ):
        self.rng = np.random.default_rng(seed)
        self.wind_speed_ms = wind_speed_ms
        self.wind_dir_from_deg = wind_dir_from_deg
        self.stability = stability
        self.equipment = {tag: e for e in layout.EQUIPMENT for tag in [e[0]]}
        self.sensors = {s[0]: s for s in layout.SENSORS}

    # -- process signals ---------------------------------------------------

    def _wind(self, t: float) -> tuple[float, float]:
        """Gentle meander, not white noise — real wind is autocorrelated."""
        speed = self.wind_speed_ms + 0.22 * math.sin(t / 37.0) + self.rng.normal(0, 0.06)
        # Direction meander is kept small: at 25 m downwind a few degrees of
        # swing moves the plume centreline further than the release itself
        # changes, which would smear the peak. The demo assumes a steady
        # north-westerly, which is what the wind rose at Fahud usually gives.
        direction = (
            self.wind_dir_from_deg
            + 1.0 * math.sin(t / 53.0)
            + self.rng.normal(0, 0.25)
        ) % 360.0
        return max(speed, 0.4), direction

    def _discharge_pressure(self, t: float, anomaly: float) -> float:
        """C-03 discharge pressure: nominal 62 barg with a small drift."""
        return 62.0 + 0.25 * math.sin(t / 61.0) + self.rng.normal(0, 0.05) + anomaly

    def _flow(self, t: float, anomaly: float) -> float:
        return 1840.0 + 12.0 * math.sin(t / 47.0) + self.rng.normal(0, 3.0) + anomaly

    # -- main loop ---------------------------------------------------------

    def generate(
        self,
        start: dt.datetime,
        duration_s: int,
        release_profile=None,
        source_tag: str = layout.DEMO_SOURCE_TAG,
        run_phase: str = "baseline",
        pressure_profile=None,
        flow_profile=None,
        equipment_state_profile=None,
        step_s: int = 1,
    ):
        """Yield one Tick per step. `release_profile(t)` returns kg CH4/h."""
        src = self.equipment[source_tag]
        source_xy = (src[3], src[4])

        for i in range(0, duration_s, step_s):
            t = float(i)
            ts = start + dt.timedelta(seconds=t)
            speed, direction = self._wind(t)
            q = float(release_profile(t)) if release_profile else 0.0

            p_anom = float(pressure_profile(t)) if pressure_profile else 0.0
            f_anom = float(flow_profile(t)) if flow_profile else 0.0
            pressure = self._discharge_pressure(t, p_anom)
            flow = self._flow(t, f_anom)

            states = {tag: e[7] for tag, e in self.equipment.items()}
            if equipment_state_profile:
                states.update(equipment_state_profile(t) or {})

            readings = []
            for tag, (_, sx, sy, base, noise) in self.sensors.items():
                # Advection delay: a sensor cannot see gas that has not arrived.
                lag = travel_time_s(source_xy, (sx, sy), speed, direction)
                q_arriving = (
                    float(release_profile(t - lag))
                    if release_profile and math.isfinite(lag) and t - lag >= 0
                    else 0.0
                )
                excess = plume_ppm(
                    q_arriving,
                    source_xy,
                    (sx, sy),
                    speed,
                    direction,
                    self.stability,
                )
                ppm = base + self.rng.normal(0, noise) + excess
                readings.append(
                    {
                        "sensor_tag": tag,
                        "sensor_id": layout.sensor_id(tag),
                        "ch4_ppm": round(max(ppm, 0.0), 4),
                        "pressure_barg": round(pressure, 3),
                        "flow_kg_h": round(flow, 2),
                        "equipment_state": states.get(layout.DEMO_SOURCE_TAG, "running"),
                        "quality": 1.0,
                    }
                )

            yield Tick(
                ts=ts,
                facility_id=layout.FACILITY_ID,
                readings=readings,
                weather={
                    "wind_speed_ms": round(speed, 3),
                    "wind_dir_deg": round(direction, 2),
                    "temperature_c": round(33.0 + 1.2 * math.sin(t / 900.0), 2),
                    "pressure_hpa": 1006.0,
                    "stability_class": self.stability,
                },
                equipment_states=states,
                run_phase=run_phase,
            )
