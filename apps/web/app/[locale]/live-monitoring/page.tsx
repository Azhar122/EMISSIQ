"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { Schematic } from "@/components/Schematic";
import { EquipmentPanel } from "@/components/EquipmentPanel";
import { ReplayScrubber } from "@/components/ReplayScrubber";
import { useDemo } from "@/components/DemoProvider";
import { useEventReplay } from "@/lib/useEventReplay";
import { api, EventSummary, FacilityDetail } from "@/lib/api";
import type { TwinFrame } from "@/components/Schematic3D";

// WebGL needs the browser; skip SSR for the 3D twin.
const Schematic3D = dynamic(() => import("@/components/Schematic3D").then((m) => m.Schematic3D), {
  ssr: false,
  loading: () => (
    <div style={{ height: 520, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
      Loading 3D twin…
    </div>
  ),
});

export default function LiveMonitoringPage() {
  const t = useTranslations();
  const demo = useDemo();
  const [mode, setMode] = useState<"3d" | "2d">("3d");
  const [source, setSource] = useState<"live" | "replay">("live");
  const [showCoverage, setShowCoverage] = useState(false);
  const [showAttribution, setShowAttribution] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [replayEventId, setReplayEventId] = useState<string | null>(null);
  const [facility, setFacility] = useState<FacilityDetail | null>(null);

  useEffect(() => {
    api.get<FacilityDetail>("/api/facilities/FAC-FAHUD-DEMO").then(setFacility).catch(() => {});
  }, []);

  // Replay target: the running demo event if there is one, else the most
  // recent demo-run event on record.
  useEffect(() => {
    if (demo.eventId) { setReplayEventId(demo.eventId); return; }
    api.get<EventSummary[]>("/api/events?limit=50").then((rows) => {
      const latest = rows.find((r) => r.run_phase === "demo-event") ?? null;
      setReplayEventId(latest?.id ?? null);
    }).catch(() => {});
  }, [demo.eventId, demo.version]);

  const replay = useEventReplay(source === "replay" ? replayEventId : null);

  // Live mode switches automatically to the socket while the demo streams.
  useEffect(() => {
    if (demo.running) setSource("live");
  }, [demo.running]);

  const frameOverride: TwinFrame | null = useMemo(() => {
    if (source !== "replay" || !replay.frame) return null;
    return {
      sensors: replay.frame.sensors,
      wind_speed_ms: replay.frame.wind_speed_ms,
      wind_dir_deg: replay.frame.wind_dir_deg,
      pressure_barg: replay.frame.pressure_barg,
      flow_kg_h: replay.frame.flow_kg_h,
    };
  }, [source, replay.frame]);

  // Live values for the inspection panel: from the replay frame when
  // scrubbing, from the socket otherwise.
  const livePressure = frameOverride?.pressure_barg ?? demo.lastTick?.pressure_barg ?? null;
  const liveFlow = frameOverride?.flow_kg_h ?? demo.lastTick?.flow_kg_h ?? null;
  const liveCh4 = useMemo(() => {
    if (!facility) return null;
    const sensors = frameOverride?.sensors ?? new Map(demo.lastTick?.sensors.map((s) => [s.tag, s.ch4_ppm]) ?? []);
    let max = 0;
    facility.sensors.forEach((s) => {
      const v = sensors.get(s.tag);
      if (v !== undefined && !Number.isNaN(v)) max = Math.max(max, v - s.baseline_ppm);
    });
    return max;
  }, [facility, frameOverride, demo.lastTick]);

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("liveMonitoring.title")}</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("liveMonitoring.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="tabs">
            <div className={`tab ${mode === "3d" ? "active" : ""}`} onClick={() => setMode("3d")}>3D Twin</div>
            <div className={`tab ${mode === "2d" ? "active" : ""}`} onClick={() => setMode("2d")}>2D Plan</div>
          </div>
          <div className="tabs">
            <div className={`tab ${source === "live" ? "active" : ""}`} onClick={() => setSource("live")}>Live</div>
            <div
              className={`tab ${source === "replay" ? "active" : ""}`}
              style={{ opacity: replayEventId ? 1 : 0.4 }}
              onClick={() => replayEventId && setSource("replay")}
              title={replayEventId ? `Replay ${replayEventId}` : "Run the demo first"}
            >
              Replay
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Toggle on={showAttribution} onClick={() => setShowAttribution((v) => !v)} label="Attribution overlay" />
        <Toggle on={showCoverage} onClick={() => setShowCoverage((v) => !v)} label="Coverage / blind spots" />
        {mode === "2d" && <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Overlays and inspection are available in the 3D twin.</span>}
      </div>

      <div className="flex gap-5 items-start" style={{ flexWrap: "wrap" }}>
        <div className="flex-1 flex flex-col gap-4" style={{ minWidth: 0, flexBasis: 640 }}>
          <div className="panel">
            {mode === "3d" ? (
              <Schematic3D
                frameOverride={frameOverride}
                showCoverage={showCoverage}
                showAttribution={showAttribution}
                forceAttribution={source === "replay" ? replay.attributedVisible : false}
                selectedTag={selectedTag}
                onSelect={setSelectedTag}
              />
            ) : (
              <Schematic />
            )}
          </div>

          {source === "replay" && replayEventId && replay.ready && (
            <ReplayScrubber
              eventId={replayEventId}
              elapsed={replay.frame?.elapsed_s ?? 0}
              duration={replay.durationS}
              milestones={replay.milestones}
              playing={replay.playing}
              speed={replay.speed}
              onSeek={replay.seekElapsed}
              onPlay={replay.play}
              onPause={replay.pause}
              onSpeed={replay.setSpeed}
            />
          )}
          {source === "replay" && replayEventId && !replay.ready && (
            <div className="panel" style={{ fontSize: 12.5, color: "var(--text-muted)" }}>Loading stored event data…</div>
          )}
        </div>

        {selectedTag && (
          <div style={{ width: 330, flexShrink: 0 }}>
            <EquipmentPanel
              tag={selectedTag}
              livePressure={livePressure}
              liveFlow={liveFlow}
              liveCh4={liveCh4}
              onClose={() => setSelectedTag(null)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Toggle({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-full px-3 py-1.5"
      style={{
        fontSize: 12.5,
        fontWeight: 600,
        background: on ? "var(--green)" : "#fff",
        color: on ? "#fff" : "var(--text-dark)",
        border: `1px solid ${on ? "var(--green)" : "var(--border)"}`,
      }}
    >
      <span className="inline-block rounded-full" style={{ width: 8, height: 8, background: on ? "var(--peach)" : "var(--border)" }} />
      {label}
    </button>
  );
}
