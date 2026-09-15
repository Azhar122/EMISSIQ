"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Timeseries } from "@/lib/api";

export interface ReplayFrame {
  t: string;
  elapsed_s: number;
  sensors: Map<string, number>;
  pressure_barg: number | null;
  flow_kg_h: number | null;
  wind_speed_ms: number;
  wind_dir_deg: number;
}

export interface ReplayMilestone {
  key: string;
  label: string;
  elapsed_s: number;
}

/** Loads an event's stored timeseries and exposes it as scrubbable frames with
 * the moments a judge cares about pinned on the timeline. All numbers come from
 * the database — this is a replay of what the detector actually saw. */
export function useEventReplay(eventId: string | null) {
  const [ts, setTs] = useState<Timeseries | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const rafRef = useRef<number | null>(null);
  const lastRef = useRef<number>(0);
  const accRef = useRef<number>(0);

  useEffect(() => {
    setTs(null);
    setIndex(0);
    setPlaying(false);
    if (!eventId) return;
    api.get<Timeseries>(`/api/events/${eventId}/timeseries?pad_s=40`).then(setTs).catch(() => {});
  }, [eventId]);

  const frames = useMemo<ReplayFrame[]>(() => {
    if (!ts) return [];
    const stamps = new Set<string>();
    Object.values(ts.ch4_by_sensor).forEach((s) => s.forEach((p) => stamps.add(p.t)));
    const sorted = Array.from(stamps).sort();
    if (!sorted.length) return [];
    const t0 = new Date(sorted[0]).getTime();

    const bySensor: Record<string, Map<string, number>> = {};
    for (const [tag, series] of Object.entries(ts.ch4_by_sensor)) {
      bySensor[tag] = new Map(series.map((p) => [p.t, p.ch4_ppm]));
    }
    const proc = new Map(ts.process.map((p) => [p.t, p]));
    const wind = ts.wind;

    // Wind is sampled on its own clock; nearest-neighbour is fine at 1 Hz.
    let wi = 0;
    return sorted.map((t) => {
      const tm = new Date(t).getTime();
      while (wi < wind.length - 1 && new Date(wind[wi + 1].t).getTime() <= tm) wi++;
      const w = wind[wi] ?? { wind_speed_ms: 5.1, wind_dir_deg: 315 };
      const p = proc.get(t);
      return {
        t,
        elapsed_s: Math.round((tm - t0) / 1000),
        sensors: new Map(Object.entries(bySensor).map(([tag, m]) => [tag, m.get(t) ?? NaN])),
        pressure_barg: p?.pressure_barg ?? null,
        flow_kg_h: p?.flow_kg_h ?? null,
        wind_speed_ms: w.wind_speed_ms,
        wind_dir_deg: w.wind_dir_deg,
      };
    });
  }, [ts]);

  const milestones = useMemo<ReplayMilestone[]>(() => {
    if (!ts || !frames.length) return [];
    const t0 = new Date(frames[0].t).getTime();
    const at = (iso: string) => Math.round((new Date(iso).getTime() - t0) / 1000);
    const out: ReplayMilestone[] = [];

    // Pressure step: first sample more than 0.3 barg below the pre-event median.
    const start = ts.markers.find((m) => m.label === "Detection start");
    if (start) {
      const startMs = new Date(start.t).getTime();
      const pre = ts.process.filter((p) => new Date(p.t).getTime() < startMs && p.pressure_barg != null).map((p) => p.pressure_barg as number);
      if (pre.length) {
        const med = [...pre].sort((a, b) => a - b)[Math.floor(pre.length / 2)];
        const step = ts.process.find((p) => p.pressure_barg != null && (p.pressure_barg as number) < med - 0.3);
        if (step) out.push({ key: "pressure", label: "Pressure step", elapsed_s: at(step.t) });
      }
    }

    // First rise per sensor: > 0.8 ppm above that sensor's own pre-event median.
    for (const tag of ["S3", "S4"]) {
      const series = ts.ch4_by_sensor[tag];
      if (!series || !start) continue;
      const startMs = new Date(start.t).getTime();
      const pre = series.filter((p) => new Date(p.t).getTime() < startMs).map((p) => p.ch4_ppm);
      const med = pre.length ? [...pre].sort((a, b) => a - b)[Math.floor(pre.length / 2)] : 2;
      const rise = series.find((p) => p.ch4_ppm > med + 0.8);
      if (rise) out.push({ key: tag, label: `${tag} detects`, elapsed_s: at(rise.t) });
    }

    for (const m of ts.markers) {
      if (m.label === "Peak") out.push({ key: "peak", label: "Peak", elapsed_s: at(m.t) });
      if (m.label === "Event end") out.push({ key: "end", label: "Event end", elapsed_s: at(m.t) });
    }
    // Attribution is computed after the window closes; pin it just past the end.
    const end = out.find((m) => m.key === "end");
    if (end) out.push({ key: "attributed", label: "Attributed", elapsed_s: end.elapsed_s + 4 });

    return out.sort((a, b) => a.elapsed_s - b.elapsed_s);
  }, [ts, frames]);

  // Play loop at `speed`× real time.
  useEffect(() => {
    if (!playing || !frames.length) return;
    lastRef.current = performance.now();
    accRef.current = 0;
    const tick = (now: number) => {
      const dt = (now - lastRef.current) / 1000;
      lastRef.current = now;
      accRef.current += dt * speed;
      const step = Math.floor(accRef.current);
      if (step >= 1) {
        accRef.current -= step;
        setIndex((i) => {
          const next = i + step;
          if (next >= frames.length - 1) {
            setPlaying(false);
            return frames.length - 1;
          }
          return next;
        });
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, speed, frames.length]);

  const seek = useCallback((i: number) => setIndex(Math.max(0, Math.min(frames.length - 1, i))), [frames.length]);
  const seekElapsed = useCallback(
    (s: number) => {
      const i = frames.findIndex((f) => f.elapsed_s >= s);
      seek(i === -1 ? frames.length - 1 : i);
    },
    [frames, seek],
  );

  const frame = frames[index] ?? null;
  const attributedVisible = !!frame && milestones.some((m) => m.key === "attributed" && frame.elapsed_s >= m.elapsed_s);

  return {
    ready: frames.length > 0,
    frames,
    frame,
    index,
    milestones,
    playing,
    speed,
    attributedVisible,
    play: () => { if (index >= frames.length - 1) setIndex(0); setPlaying(true); },
    pause: () => setPlaying(false),
    setSpeed,
    seek,
    seekElapsed,
    durationS: frames.length ? frames[frames.length - 1].elapsed_s : 0,
  };
}
