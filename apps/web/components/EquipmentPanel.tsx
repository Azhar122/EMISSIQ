"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale } from "next-intl";
import { api } from "@/lib/api";
import { fmtNum, fmtDateTime, severityBadgeClass } from "@/lib/format";

interface EquipmentInfo {
  id: string;
  tag: string;
  name: string;
  type: string;
  operating_state: string;
  criticality: number;
  current_event: {
    id: string; status: string; peak_emission_rate_kg_h: number | null; total_mass_kg: number | null;
    uncertainty_pct: number | null; attribution_confidence: number | null; priority: string | null;
  } | null;
  maintenance: { task: string; discipline: string; performed_at: string | null; due_at: string | null; overdue: boolean; notes: string }[];
  overdue_count: number;
  previous_events: { id: string; started_at: string; peak_emission_rate_kg_h: number | null; severity: string; status: string }[];
  recommended_inspection: { title: string; discipline: string; steps: string[]; linked_overdue_task: string | null };
}

export function EquipmentPanel({
  tag,
  livePressure,
  liveFlow,
  liveCh4,
  onClose,
}: {
  tag: string;
  livePressure: number | null;
  liveFlow: number | null;
  /** highest live excess at the nearest downwind sensor, ppm */
  liveCh4: number | null;
  onClose: () => void;
}) {
  const locale = useLocale();
  const [info, setInfo] = useState<EquipmentInfo | null>(null);

  useEffect(() => {
    setInfo(null);
    api.get<EquipmentInfo>(`/api/equipment/${tag}`).then(setInfo).catch(() => {});
  }, [tag]);

  const isCompressor = info?.type === "compressor";

  return (
    <div className="panel" style={{ padding: 18 }}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{tag}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{info?.name ?? "…"}</div>
        </div>
        <button onClick={onClose} style={{ color: "var(--text-muted)", fontSize: 18, lineHeight: 1 }}>×</button>
      </div>

      {info && (
        <>
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span className="badge badge-info">{info.operating_state}</span>
            <span className="badge badge-grey">criticality {Math.round(info.criticality * 100)}%</span>
            {info.overdue_count > 0 && <span className="badge badge-critical">{info.overdue_count} overdue</span>}
          </div>

          <Section title="Live process">
            <div className="grid grid-cols-2 gap-2">
              <Metric label="Discharge pressure" value={isCompressor && livePressure != null ? `${livePressure.toFixed(2)} barg` : "—"} />
              <Metric label="Flow" value={isCompressor && liveFlow != null ? `${fmtNum(liveFlow, 0)} kg/h` : "—"} />
              <Metric label="CH₄ nearby (excess)" value={liveCh4 != null ? `${liveCh4.toFixed(1)} ppm` : "0.0 ppm"} accent={liveCh4 != null && liveCh4 > 0.8 ? "var(--red)" : undefined} />
              <Metric
                label="Est. emission rate"
                value={info.current_event?.peak_emission_rate_kg_h != null ? `${fmtNum(info.current_event.peak_emission_rate_kg_h, 1)} kg/h` : "—"}
                sub={info.current_event?.uncertainty_pct != null ? `±${fmtNum(info.current_event.uncertainty_pct, 0)}%` : undefined}
              />
            </div>
          </Section>

          {info.current_event && (
            <Section title="Current event">
              <Link href={`/${locale}/events/${info.current_event.id}`} className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: "var(--red-bg)", fontSize: 12.5 }}>
                <span style={{ fontWeight: 700, color: "var(--red)" }}>{info.current_event.id}</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {info.current_event.priority} · {Math.round((info.current_event.attribution_confidence ?? 0) * 100)}% conf →
                </span>
              </Link>
            </Section>
          )}

          <Section title="Maintenance status">
            {info.maintenance.slice(0, 3).map((m, i) => (
              <div key={i} className="flex items-start justify-between gap-2 py-1.5" style={{ borderBottom: "1px solid var(--border)", fontSize: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, color: m.overdue ? "var(--red)" : "var(--text-dark)" }}>{m.task}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: 11 }}>{m.discipline} · due {fmtDateTime(m.due_at, locale)}</div>
                </div>
                {m.overdue && <span className="badge badge-critical" style={{ fontSize: 10 }}>OVERDUE</span>}
              </div>
            ))}
          </Section>

          <Section title={`Previous events (${info.previous_events.length})`}>
            {info.previous_events.length === 0 && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>None on record.</div>}
            {info.previous_events.slice(0, 4).map((e) => (
              <Link key={e.id} href={`/${locale}/events/${e.id}`} className="flex items-center justify-between py-1" style={{ fontSize: 12 }}>
                <span style={{ color: "var(--green)", fontWeight: 600 }}>{e.id}</span>
                <span className="flex items-center gap-2">
                  <span style={{ color: "var(--text-muted)" }}>{fmtNum(e.peak_emission_rate_kg_h, 1)} kg/h</span>
                  <span className={`badge ${severityBadgeClass(e.severity)}`} style={{ fontSize: 10, padding: "2px 7px" }}>{e.severity}</span>
                </span>
              </Link>
            ))}
          </Section>

          <Section title="Recommended inspection">
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>{info.recommended_inspection.title}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{info.recommended_inspection.discipline}</div>
            <ol style={{ margin: 0, paddingLeft: 16, fontSize: 11.5, color: "var(--text-dark)", lineHeight: 1.6 }}>
              {info.recommended_inspection.steps.slice(0, 3).map((s, i) => <li key={i}>{s}</li>)}
            </ol>
            {info.recommended_inspection.linked_overdue_task && (
              <div style={{ fontSize: 11, color: "var(--red)", marginTop: 6 }}>
                Linked overdue task: {info.recommended_inspection.linked_overdue_task}
              </div>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  );
}

function Metric({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-lg p-2.5" style={{ background: "var(--cream)" }}>
      <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: accent }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}
