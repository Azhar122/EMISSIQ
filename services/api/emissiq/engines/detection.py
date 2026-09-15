"""Deterministic methane event detection.

No model, no LLM. A rolling robust baseline plus a z-score gate with hysteresis
and a minimum duration, which is what a field deployment would actually use to
keep intermittent releases from flapping the alarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

# Tunables live here so the whole detection contract is readable in one place.
DETECTION_CONFIG = {
    "baseline_window_s": 600,  # robust baseline: 10-minute rolling median
    # Sigma is estimated over the same long window as the baseline. A short
    # window lets the excursion itself inflate sigma, and the event then never
    # settles back below the exit threshold.
    "stats_window_s": 600,
    "z_enter": 4.0,  # z above which a candidate event opens
    "z_exit": 1.5,  # hysteresis: must fall below this to close
    "abs_min_ppm_above_baseline": 0.8,  # ignore statistically loud but tiny excursions
    "min_duration_s": 10,  # reject single-sample spikes
    "exit_persistence_s": 8,  # must stay quiet this long before closing
    # A single noisy sample should not restart the exit countdown, so the quiet
    # window tolerates this fraction of samples still above z_exit.
    "exit_noise_tolerance": 0.25,
    "min_sigma_ppm": 0.05,  # floor on sigma so a flat sensor cannot divide by ~0
}


@dataclass
class DetectedEvent:
    sensor_id: str
    started_at: pd.Timestamp
    peak_at: pd.Timestamp
    ended_at: pd.Timestamp | None
    duration_s: float
    baseline_ppm: float
    peak_ppm: float
    peak_zscore: float
    peak_excess_ppm: float
    max_rate_ppm_s: float
    confidence: float
    config: dict = field(default_factory=lambda: dict(DETECTION_CONFIG))

    def as_dict(self) -> dict:
        d = asdict(self)
        for key in ("started_at", "peak_at", "ended_at"):
            d[key] = d[key].isoformat() if d[key] is not None else None
        return d


def _rolling_stats(series: pd.Series, window_s: int, sample_s: float) -> pd.Series:
    """Rolling window expressed in samples, with a sane minimum sample count."""
    n = max(3, int(round(window_s / max(sample_s, 1e-6))))
    return series.rolling(window=n, min_periods=3)


def compute_signal(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Annotate a single sensor's CH4 series with baseline, sigma, z and slope.

    `df` needs columns `ts` (tz-aware) and `ch4_ppm`, ordered ascending.
    """
    cfg = {**DETECTION_CONFIG, **(cfg or {})}
    out = df.sort_values("ts").reset_index(drop=True).copy()
    if len(out) < 3:
        return out.assign(baseline=np.nan, sigma=np.nan, zscore=np.nan, rate_ppm_s=np.nan)

    sample_s = float(np.median(np.diff(out["ts"].astype("int64") // 10**9)) or 1.0)

    # Median baseline and MAD-derived sigma resist the excursion we are hunting:
    # a mean/std baseline would absorb the leak and hide it from itself.
    roll = _rolling_stats(out["ch4_ppm"], cfg["baseline_window_s"], sample_s)
    out["baseline"] = roll.median().bfill()

    resid = (out["ch4_ppm"] - out["baseline"]).abs()
    mad = _rolling_stats(resid, cfg["stats_window_s"], sample_s).median().bfill()
    out["sigma"] = np.maximum(mad * 1.4826, cfg["min_sigma_ppm"])

    out["excess"] = out["ch4_ppm"] - out["baseline"]
    out["zscore"] = out["excess"] / out["sigma"]
    out["rate_ppm_s"] = out["ch4_ppm"].diff() / sample_s
    out["sample_s"] = sample_s
    return out


def detect_events(
    df: pd.DataFrame, sensor_id: str, cfg: dict | None = None
) -> list[DetectedEvent]:
    """Find start / peak / end for every excursion on one sensor."""
    cfg = {**DETECTION_CONFIG, **(cfg or {})}
    sig = compute_signal(df, cfg)
    if "zscore" not in sig or sig["zscore"].isna().all():
        return []

    sample_s = float(sig["sample_s"].iloc[0])
    exit_samples = max(1, int(round(cfg["exit_persistence_s"] / sample_s)))

    max_noisy = int(exit_samples * cfg["exit_noise_tolerance"])

    events: list[DetectedEvent] = []
    open_idx: int | None = None
    quiet_start: int | None = None  # first sample of the current quiet run
    noisy_in_run = 0

    for i, row in sig.iterrows():
        z, excess = row["zscore"], row["excess"]
        triggered = (
            z >= cfg["z_enter"] and excess >= cfg["abs_min_ppm_above_baseline"]
        )

        if open_idx is None:
            if triggered:
                open_idx = i
                quiet_start, noisy_in_run = None, 0
            continue

        # Event is open — look for a sustained return to baseline.
        if z <= cfg["z_exit"]:
            if quiet_start is None:
                quiet_start, noisy_in_run = i, 0
        elif quiet_start is not None:
            noisy_in_run += 1
            if triggered or noisy_in_run > max_noisy:
                quiet_start, noisy_in_run = None, 0  # genuinely back above threshold

        settled = quiet_start is not None and (i - quiet_start + 1) >= exit_samples
        if settled or i == len(sig) - 1:
            end_idx = quiet_start if quiet_start is not None else i
            ev = _finalise(sig, open_idx, end_idx, sensor_id, cfg, sample_s)
            if ev is not None:
                events.append(ev)
            open_idx, quiet_start, noisy_in_run = None, None, 0

    return events


def _finalise(
    sig: pd.DataFrame,
    start_idx: int,
    end_idx: int,
    sensor_id: str,
    cfg: dict,
    sample_s: float,
) -> DetectedEvent | None:
    window = sig.iloc[start_idx : end_idx + 1]
    if window.empty:
        return None

    started = window["ts"].iloc[0]
    ended = window["ts"].iloc[-1]
    duration = float((ended - started).total_seconds())
    if duration < cfg["min_duration_s"]:
        return None  # too short to be a real release; drop it silently

    peak_row = window.loc[window["ch4_ppm"].idxmax()]
    peak_z = float(peak_row["zscore"])

    # Confidence blends how far above the noise the peak sat with how long the
    # excursion persisted. Both are needed: a tall spike of one sample is noise,
    # a long drift at z=4 is a real but weak release.
    z_term = min(1.0, peak_z / 12.0)
    dur_term = min(1.0, duration / 60.0)
    confidence = round(0.65 * z_term + 0.35 * dur_term, 3)

    return DetectedEvent(
        sensor_id=sensor_id,
        started_at=started,
        peak_at=peak_row["ts"],
        ended_at=ended,
        duration_s=duration,
        baseline_ppm=round(float(window["baseline"].iloc[0]), 4),
        peak_ppm=round(float(peak_row["ch4_ppm"]), 4),
        peak_zscore=round(peak_z, 3),
        peak_excess_ppm=round(float(peak_row["excess"]), 4),
        max_rate_ppm_s=round(float(window["rate_ppm_s"].max()), 4),
        confidence=confidence,
    )


def detect_across_sensors(
    readings: pd.DataFrame, cfg: dict | None = None
) -> dict[str, list[DetectedEvent]]:
    """Run detection per sensor. Returns sensor_id -> events, first-detection order."""
    result: dict[str, list[DetectedEvent]] = {}
    for sensor_id, group in readings.groupby("sensor_id"):
        found = detect_events(group, str(sensor_id), cfg)
        if found:
            result[str(sensor_id)] = found
    return dict(
        sorted(result.items(), key=lambda kv: kv[1][0].started_at)
    )
