"use client";

import type { ReplayMilestone } from "@/lib/useEventReplay";

const MILESTONE_COLOR: Record<string, string> = {
  pressure: "var(--blue)",
  S3: "var(--amber)",
  S4: "var(--orange)",
  peak: "var(--red)",
  end: "var(--normal-green)",
  attributed: "var(--umber)",
};

export function ReplayScrubber({
  elapsed,
  duration,
  milestones,
  playing,
  speed,
  onSeek,
  onPlay,
  onPause,
  onSpeed,
  eventId,
}: {
  elapsed: number;
  duration: number;
  milestones: ReplayMilestone[];
  playing: boolean;
  speed: number;
  onSeek: (s: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSpeed: (s: number) => void;
  eventId: string;
}) {
  const passed = milestones.filter((m) => elapsed >= m.elapsed_s);
  const current = passed[passed.length - 1];

  return (
    <div className="panel" style={{ padding: "14px 18px" }}>
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <button className="btn-primary" style={{ padding: "7px 14px", minWidth: 84, justifyContent: "center" }} onClick={playing ? onPause : onPlay}>
          {playing ? "❚❚ Pause" : "▶ Replay"}
        </button>
        <div className="tabs" style={{ padding: 3 }}>
          {[1, 2, 4].map((s) => (
            <div key={s} className={`tab ${speed === s ? "active" : ""}`} style={{ padding: "5px 11px", fontSize: 12 }} onClick={() => onSpeed(s)}>
              {s}×
            </div>
          ))}
        </div>
        <span style={{ fontSize: 12.5, fontWeight: 700, minWidth: 90 }}>
          T+{elapsed}s <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>/ {duration}s</span>
        </span>
        <span style={{ fontSize: 12, color: current ? MILESTONE_COLOR[current.key] : "var(--text-muted)", fontWeight: 700 }}>
          {current ? current.label : "Baseline"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-muted)" }}>
          Replaying stored sensor data for {eventId}
        </span>
      </div>

      <div className="relative" style={{ height: 38 }}>
        <input
          type="range"
          min={0}
          max={duration}
          value={elapsed}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="w-full absolute"
          style={{ top: 4, accentColor: "var(--green)" }}
        />
        {milestones.map((m) => {
          const left = duration ? (m.elapsed_s / duration) * 100 : 0;
          const hit = elapsed >= m.elapsed_s;
          return (
            <button
              key={m.key}
              onClick={() => onSeek(m.elapsed_s)}
              title={`${m.label} — T+${m.elapsed_s}s`}
              className="absolute"
              style={{ left: `${left}%`, top: 22, transform: "translateX(-50%)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
            >
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: MILESTONE_COLOR[m.key], opacity: hit ? 1 : 0.35, margin: "0 auto 2px" }} />
              <div style={{ fontSize: 9.5, fontWeight: 700, color: MILESTONE_COLOR[m.key], opacity: hit ? 1 : 0.5, whiteSpace: "nowrap" }}>
                {m.label}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
