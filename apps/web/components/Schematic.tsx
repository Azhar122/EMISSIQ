"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { api, FacilityDetail, Candidate } from "@/lib/api";
import { useDemo } from "./DemoProvider";

const FACILITY_ID = "FAC-FAHUD-DEMO";
const EXTENT = 130; // metres either side of origin, matches the layout module

function sevColor(ppm: number, baseline: number): string {
  const excess = ppm - baseline;
  if (excess > 15) return "var(--red)";
  if (excess > 3) return "var(--orange)";
  if (excess > 0.8) return "var(--amber)";
  return "var(--normal-green)";
}

const EQUIP_ICON: Record<string, string> = {
  compressor: "⚙",
  control_valve: "⏚",
  tank_vent: "▽",
  separator: "◫",
  knockout_drum: "◒",
  pig_launcher: "▶",
};

export function Schematic({ compact = false }: { compact?: boolean }) {
  const t = useTranslations();
  const demo = useDemo();
  const [facility, setFacility] = useState<FacilityDetail | null>(null);
  const [leaderTag, setLeaderTag] = useState<string | null>(null);

  useEffect(() => {
    api.get<FacilityDetail>(`/api/facilities/${FACILITY_ID}`).then(setFacility).catch(() => {});
  }, []);

  useEffect(() => {
    if (!demo.eventId) {
      setLeaderTag(null);
      return;
    }
    const attributedStages = ["attributed", "quantified", "prioritised", "investigated", "recommended", "work_order", "repaired", "verifying", "avoided"];
    if (!demo.currentStageKey || !attributedStages.includes(demo.currentStageKey)) return;
    api.get<{ candidates: Candidate[] }>(`/api/events/${demo.eventId}/candidates`).then((d) => {
      setLeaderTag(d.candidates[0]?.tag ?? null);
    }).catch(() => {});
  }, [demo.eventId, demo.currentStageKey]);

  const sensorLevels = useMemo(() => {
    const map = new Map<string, number>();
    demo.lastTick?.sensors.forEach((s) => map.set(s.tag, s.ch4_ppm));
    return map;
  }, [demo.lastTick]);

  const wind = demo.lastTick?.weather;
  const eventLive = demo.lastTick && demo.lastTick.run_phase !== "baseline";

  // Project plant-frame metres (x east, y north) into SVG space (y flipped).
  const toSvg = (x: number, y: number) => {
    const px = 50 + (x / EXTENT) * 42;
    const py = 50 - (y / EXTENT) * 42;
    return [px, py] as const;
  };

  const windDir = wind?.wind_dir_deg ?? 315;
  const plumeToDeg = (windDir + 180) % 360;

  return (
    <div>
      <div
        className="relative overflow-hidden"
        style={{
          background: "#F1E9DE",
          borderRadius: 12,
          height: compact ? 260 : 460,
          border: "1px solid var(--border)",
        }}
      >
        <div
          className="absolute rounded-xl bg-white flex items-center gap-2.5 px-3.5 py-2.5 z-10"
          style={{ top: 14, left: 14, boxShadow: "var(--shadow)" }}
        >
          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{t("liveMonitoring.wind")}</span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>
            {wind ? `${wind.wind_speed_ms.toFixed(1)} m/s @ ${Math.round(wind.wind_dir_deg)}°` : "5.1 m/s @ 315°"}
          </span>
        </div>

        {!compact && (
          <div
            className="absolute rounded-xl bg-white px-3.5 py-2.5 z-10"
            style={{ top: 14, right: 14, boxShadow: "var(--shadow)", fontSize: 12 }}
          >
            {[
              [t("liveMonitoring.legendNormal"), "var(--normal-green)"],
              [t("liveMonitoring.legendElevated"), "var(--amber)"],
              [t("liveMonitoring.legendCritical"), "var(--red)"],
            ].map(([label, color]) => (
              <div key={label as string} className="flex items-center gap-1.5 mb-1 last:mb-0">
                <span className="inline-block rounded-full" style={{ width: 8, height: 8, background: color as string }} />
                {label}
              </div>
            ))}
          </div>
        )}

        <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          {/* pipelines */}
          {facility?.equipment && (
            <>
              {[
                ["SEP-01", "C-03"], ["C-03", "T-02"], ["C-02", "V-14"],
                ["V-14", "C-03"], ["C-03", "PIG-01"], ["KOD-01", "C-02"],
              ].map(([a, b]) => {
                const ea = facility.equipment.find((e) => e.tag === a);
                const eb = facility.equipment.find((e) => e.tag === b);
                if (!ea || !eb) return null;
                const [x1, y1] = toSvg(ea.x_m, ea.y_m);
                const [x2, y2] = toSvg(eb.x_m, eb.y_m);
                return <line key={`${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#D8CBBA" strokeWidth={0.6} />;
              })}
            </>
          )}

          {/* plume cone, only while an event is live */}
          {eventLive && (
            <g opacity={0.35}>
              <defs>
                <radialGradient id="plumeGrad" cx="0%" cy="50%" r="80%">
                  <stop offset="0%" stopColor="var(--red)" stopOpacity={0.55} />
                  <stop offset="100%" stopColor="var(--red)" stopOpacity={0} />
                </radialGradient>
              </defs>
              {(() => {
                const src = facility?.equipment.find((e) => e.tag === "C-03");
                if (!src) return null;
                const [sx, sy] = toSvg(src.x_m, src.y_m);
                return (
                  <ellipse
                    cx={sx}
                    cy={sy}
                    rx={26}
                    ry={10}
                    fill="url(#plumeGrad)"
                    transform={`rotate(${plumeToDeg - 90} ${sx} ${sy}) translate(18 0)`}
                  />
                );
              })()}
            </g>
          )}

          {/* wind arrow */}
          <g transform={`translate(50 50) rotate(${plumeToDeg})`}>
            <line x1={-30} y1={0} x2={-16} y2={0} stroke="var(--blue)" strokeWidth={0.8} opacity={0.5} />
            <polygon points="-16,-1.6 -12,0 -16,1.6" fill="var(--blue)" opacity={0.5} />
          </g>

          {/* equipment */}
          {facility?.equipment.map((eq) => {
            const [x, y] = toSvg(eq.x_m, eq.y_m);
            const isLeader = leaderTag === eq.tag;
            return (
              <g key={eq.id}>
                {isLeader && <circle cx={x} cy={y} r={5.5} fill="none" stroke="var(--red)" strokeWidth={0.8}>
                  <animate attributeName="r" values="4;6.5;4" dur="1.6s" repeatCount="indefinite" />
                </circle>}
                <circle cx={x} cy={y} r={2.6} fill={isLeader ? "var(--red)" : "var(--umber)"} stroke="#fff" strokeWidth={0.4} />
                <text x={x} y={y - 4} fontSize={2.6} textAnchor="middle" fill="var(--text-dark)" fontWeight={700}>
                  {eq.tag}
                </text>
              </g>
            );
          })}

          {/* sensors */}
          {facility?.sensors.map((s) => {
            const [x, y] = toSvg(s.x_m, s.y_m);
            const ppm = sensorLevels.get(s.tag) ?? s.baseline_ppm;
            const color = sevColor(ppm, s.baseline_ppm);
            const elevated = ppm - s.baseline_ppm > 0.8;
            return (
              <g key={s.id}>
                {elevated && <circle cx={x} cy={y} r={3.6} fill={color} opacity={0.3}>
                  <animate attributeName="r" values="2.5;4.5;2.5" dur="1s" repeatCount="indefinite" />
                </circle>}
                <rect x={x - 1.6} y={y - 1.6} width={3.2} height={3.2} fill={color} stroke="#fff" strokeWidth={0.3} />
                <text x={x} y={y + 4.5} fontSize={2.4} textAnchor="middle" fill="var(--text-dark)" fontWeight={600}>
                  {s.tag}
                </text>
                {!compact && elevated && (
                  <text x={x} y={y - 3.2} fontSize={2.2} textAnchor="middle" fill={color} fontWeight={700}>
                    {ppm.toFixed(1)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
