"""Fahud demonstration facility layout.

Coordinates are metres in a local plant frame, +x east / +y north, origin at
Compressor C-03. The geometry is chosen so the demo scenario is physically
self-consistent: with the demo wind, S3 sits 25 m downwind of C-03 and S4 sits
51 m downwind, giving the 5-second detection lag the scenario calls for, while
every other sensor sits far enough off-axis to stay quiet.
"""

from __future__ import annotations

FACILITY_ID = "FAC-FAHUD-DEMO"

FACILITY = {
    "id": FACILITY_ID,
    "name": "Fahud Demonstration Facility",
    "name_ar": "منشأة فهود التجريبية",
    "region": "Central Oman",
    "block": "Block 6",
    "lat": 22.3167,
    "lon": 56.4833,
    "extent_m": 260.0,
}

# Demo meteorology: steady north-westerly, so the plume travels to the south-east.
DEMO_WIND_DIR_FROM_DEG = 315.0
DEMO_WIND_SPEED_MS = 5.1
DEMO_STABILITY = "D"
RELEASE_HEIGHT_M = 2.5

EQUIPMENT = [
    # tag, name, type, x, y, criticality, leak_propensity, operating_state
    ("C-03", "Compressor C-03", "compressor", 0.0, 0.0, 0.85, 0.55, "running"),
    ("C-02", "Compressor C-02", "compressor", -70.0, 20.0, 0.80, 0.50, "running"),
    ("V-14", "Control Valve V-14", "control_valve", -50.0, -10.0, 0.40, 0.35, "pressurised"),
    ("T-02", "Tank Vent T-02", "tank_vent", 60.0, 40.0, 0.30, 0.40, "running"),
    ("SEP-01", "Inlet Separator SEP-01", "separator", 40.0, 70.0, 0.60, 0.25, "running"),
    ("KOD-01", "Flare Knock-out Drum KOD-01", "knockout_drum", -90.0, -70.0, 0.50, 0.30, "running"),
    ("PIG-01", "Pig Launcher PIG-01", "pig_launcher", 95.0, -15.0, 0.35, 0.30, "idle"),
]

SENSORS = [
    # tag, x, y, baseline_ppm, noise_ppm
    ("S1", -80.0, 60.0, 2.05, 0.11),
    ("S2", -55.0, -25.0, 1.98, 0.12),
    ("S3", 18.0, -18.0, 2.02, 0.10),
    ("S4", 38.0, -34.0, 2.00, 0.11),
    ("S5", -95.0, -60.0, 2.04, 0.13),
    ("S6", 105.0, -5.0, 1.96, 0.12),
]

# Pipe runs drawn on the Live Monitoring schematic, by equipment tag.
PIPELINES = [
    ("SEP-01", "C-03"),
    ("C-03", "T-02"),
    ("C-02", "V-14"),
    ("V-14", "C-03"),
    ("C-03", "PIG-01"),
    ("KOD-01", "C-02"),
]

# The asset the demo release actually comes from. Attribution must rediscover
# this from the data alone; it is never handed to the scoring engine.
DEMO_SOURCE_TAG = "C-03"

# Other fields in the portfolio, so Analytics and Facilities have context.
OTHER_FACILITIES = [
    ("FAC-NIMR", "Nimr Field", "حقل نمر", "South Oman", "Block 6", 17.9, 54.3),
    ("FAC-YIBAL", "Yibal Field", "حقل يبال", "Central Oman", "Block 6", 22.2, 56.0),
    ("FAC-MARMUL", "Marmul Field", "حقل مرمول", "South Oman", "Block 6", 18.1, 55.2),
]


def equipment_id(tag: str) -> str:
    return f"EQ-{tag}"


def sensor_id(tag: str) -> str:
    return f"SEN-{tag}"
