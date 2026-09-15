"""The primary demonstration scenario — Compressor C-03, Fahud.

Anchored at T0 = 10:24:00 local. The release profile is shaped so that, after
advection to each sensor, the observable timeline lands exactly on the demo
script:

    T0+12  10:24:12   C-03 discharge pressure steps down (seal begins to pass)
    T0+17  10:24:17   S3 (25 m downwind) starts detecting elevated methane
    T0+22  10:24:22   S4 (51 m downwind) starts detecting
    T0+29  10:24:29   concentration peaks
    T0+64  10:25:04   event has cleared — short intermittent release

Travel time at the demo wind is 5 s to S3 and 10 s to S4, so the release itself
starts at T0+12 alongside the pressure change, which is why the process signal
leads the methane signal. That lead is real evidence, not decoration.
"""

from __future__ import annotations

import datetime as dt
import math

from . import layout

T0_HOUR, T0_MINUTE, T0_SECOND = 10, 24, 0

# Seconds relative to T0.
RELEASE_START_S = 11.0
RELEASE_RAMP_END_S = 24.5  # peak at source; observed at S3 five seconds later
RELEASE_DECAY_START_S = 56.0
RELEASE_END_S = 59.0

# Peak source strength, chosen so the sensor sees a realistic near-field
# concentration and the inversion recovers roughly 28-29 kg CH4/h.
PEAK_RELEASE_KG_H = 28.7

PRESSURE_DROP_BARG = -1.8  # discharge pressure step at the seal
FLOW_DROP_KG_H = -55.0

# Pre-event history written straight to the database so the detector has a
# baseline window to work with the moment the replay starts.
PRE_ROLL_S = 900
# The live replay window.
REPLAY_S = 150
# Wall-clock speed-up for the demo. 150 s of plant time in 30 s of demo time.
DEFAULT_SPEED = 5.0

# Post-repair verification replays the same window with the seal fixed.
POST_REPAIR_S = 150


def t0(day: dt.date | None = None) -> dt.datetime:
    """T0 as a UTC-aware timestamp. Oman is UTC+4, so 10:24 local is 06:24Z."""
    day = day or dt.datetime.now(dt.timezone.utc).date()
    local = dt.datetime(day.year, day.month, day.day, T0_HOUR, T0_MINUTE, T0_SECOND)
    return local.replace(tzinfo=dt.timezone(dt.timedelta(hours=4))).astimezone(
        dt.timezone.utc
    )


def release_profile(t: float) -> float:
    """kg CH4/h leaving C-03 at plant-time t seconds after T0."""
    if t < RELEASE_START_S or t >= RELEASE_END_S:
        return 0.0
    if t < RELEASE_RAMP_END_S:
        # Seal opens progressively rather than instantly.
        frac = (t - RELEASE_START_S) / (RELEASE_RAMP_END_S - RELEASE_START_S)
        return PEAK_RELEASE_KG_H * frac
    if t < RELEASE_DECAY_START_S:
        # Exponential bleed-down as upstream volume depressurises through the
        # passing seal. Gives a clean single peak at the ramp end.
        return PEAK_RELEASE_KG_H * math.exp(-(t - RELEASE_RAMP_END_S) / 14.0)
    # Seal re-seats: the last few seconds close off quickly.
    tail = PEAK_RELEASE_KG_H * math.exp(
        -(RELEASE_DECAY_START_S - RELEASE_RAMP_END_S) / 14.0
    )
    frac = (RELEASE_END_S - t) / (RELEASE_END_S - RELEASE_DECAY_START_S)
    return tail * max(frac, 0.0)


def pressure_profile(t: float) -> float:
    """Discharge pressure anomaly, in barg, relative to nominal."""
    if t < RELEASE_START_S:
        return 0.0
    if t >= RELEASE_END_S + 6:
        return 0.0
    # Steps down as the seal passes, recovers once it re-seats.
    ramp = min(1.0, (t - RELEASE_START_S) / 4.0)
    recover = 1.0 if t < RELEASE_END_S else max(0.0, 1 - (t - RELEASE_END_S) / 6.0)
    return PRESSURE_DROP_BARG * ramp * recover


def flow_profile(t: float) -> float:
    if t < RELEASE_START_S or t >= RELEASE_END_S + 6:
        return 0.0
    ramp = min(1.0, (t - RELEASE_START_S) / 5.0)
    recover = 1.0 if t < RELEASE_END_S else max(0.0, 1 - (t - RELEASE_END_S) / 6.0)
    return FLOW_DROP_KG_H * ramp * recover


def no_release(t: float) -> float:
    """Post-repair: the seal has been replaced, nothing is escaping."""
    return 0.0


# The stages the demo orchestrator walks through, in order. The UI renders this
# list directly so the sequence shown always matches the sequence executed.
DEMO_STAGES = [
    ("normal", "Normal operation", "Baseline methane, all sensors nominal"),
    ("pressure_anomaly", "Pressure anomaly", "C-03 discharge pressure steps down"),
    ("s3_detect", "Methane detected at S3", "Upwind-adjacent sensor sees elevated CH4"),
    ("s4_detect", "Methane detected at S4", "Downwind sensor confirms the plume"),
    ("event_confirmed", "Event confirmed", "Detection thresholds met and sustained"),
    ("candidates", "Source candidates generated", "Nearby assets scored against the plume"),
    ("attributed", "Compressor C-03 attributed", "Leading candidate identified"),
    ("quantified", "Quantification completed", "Emission rate and released mass estimated"),
    ("prioritised", "Priority calculated", "Deterministic priority score assigned"),
    ("investigated", "AI investigation completed", "Evidence report produced"),
    ("recommended", "Action recommended", "Inspection and discipline proposed"),
    ("work_order", "Work order created", "Routed for human approval"),
    ("repaired", "Repair completed", "Technician reports seal replaced"),
    ("verifying", "Verification in progress", "Post-repair sensor data being compared"),
    ("avoided", "Emission avoided", "Repair verified, recurring loss eliminated"),
]
