"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import {
  api, EventDetail, Candidate, Evidence, Timeseries, AIInvestigation, WorkOrder, Verification, EventSummary,
} from "@/lib/api";
import { fmtNum, fmtOmr, fmtKgH, fmtDuration, fmtPct, fmtDateTime, severityBadgeClass, statusBadgeClass } from "@/lib/format";
import { EventCharts } from "@/components/EventCharts";
import { FactorBar } from "@/components/FactorBar";
import { TakeActionModal } from "@/components/TakeActionModal";
import { Copilot } from "@/components/Copilot";
import { useDemo } from "@/components/DemoProvider";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

export default function EventWorkspacePage() {
  const t = useTranslations();
  const locale = useLocale();
  const params = useParams<{ id: string }>();
  const eventId = params.id;
  const demo = useDemo();

  const [event, setEvent] = useState<EventDetail | null>(null);
  const [timeseries, setTimeseries] = useState<Timeseries | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [investigations, setInvestigations] = useState<AIInvestigation[]>([]);
  const [similar, setSimilar] = useState<EventSummary[]>([]);
  const [verification, setVerification] = useState<Verification[]>([]);
  const [workOrder, setWorkOrder] = useState<WorkOrder | null>(null);
  const [investigating, setInvestigating] = useState(false);
  const [showAction, setShowAction] = useState(false);
  const [reportUrl, setReportUrl] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [ev, ts, cand, ev2, inv, sim, ver] = await Promise.all([
      api.get<EventDetail>(`/api/events/${eventId}`),
      api.get<Timeseries>(`/api/events/${eventId}/timeseries`),
      api.get<{ candidates: Candidate[] }>(`/api/events/${eventId}/candidates`),
      api.get<Evidence[]>(`/api/events/${eventId}/evidence`),
      api.get<AIInvestigation[]>(`/api/events/${eventId}/investigations`),
      api.get<{ events: EventSummary[] }>(`/api/events/${eventId}/similar`),
      api.get<Verification[]>(`/api/events/${eventId}/verification`).catch(() => []),
    ]);
    setEvent(ev);
    setTimeseries(ts);
    setCandidates(cand.candidates);
    setEvidence(ev2);
    setInvestigations(inv);
    setSimilar(sim.events);
    setVerification(ver);
  }, [eventId]);

  useEffect(() => { load().catch(() => {}); }, [load, demo.version]);

  useEffect(() => {
    api.get<{ work_orders: WorkOrder[] } | WorkOrder[]>(`/api/workorders?event_id=${eventId}`).then((rows: any) => {
      const list: WorkOrder[] = Array.isArray(rows) ? rows : [];
      const mine = list.find((w) => w.event_id === eventId);
      setWorkOrder(mine || null);
    }).catch(() => {});
  }, [eventId, demo.version]);

  if (!event) return <div style={{ color: "var(--text-muted)" }}>{t("common.loading")}</div>;

  const investigation = investigations[0] || null;
  const leader = candidates[0];
  const verificationLatest = verification[0];

  async function runInvestigation() {
    setInvestigating(true);
    try {
      await api.post(`/api/events/${eventId}/investigate`);
      await load();
    } finally {
      setInvestigating(false);
    }
  }

  async function generateReport() {
    const r = await api.post<{ id: string }>(`/api/reports/${eventId}`);
    setReportUrl(`/${locale}/events/${eventId}/report/${r.id}`);
  }

  return (
    <div>
      <Link href={`/${locale}/events`} style={{ fontSize: 13, fontWeight: 600, color: "var(--green)" }}>
        ← {t("workspace.back")}
      </Link>

      {/* Header */}
      <div className="panel mt-3 mb-5">
        <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "var(--text-dark)" }}>{event.id}</h1>
              <span className={`badge ${severityBadgeClass(event.severity)}`}>{event.severity}</span>
              <span className={`badge ${statusBadgeClass(event.status)}`}>{event.status}</span>
              {event.is_simulated && <span className="tag-simulated">{t("common.simulatedData")}</span>}
            </div>
            <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
              {event.equipment_name ? `${event.equipment_name} (${event.equipment_tag})` : "Unattributed"} — {event.facility_name}
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={generateReport}>{t("workspace.generateReport")}</button>
            <button className="btn-danger" onClick={() => setShowAction(true)}>{t("common.takeAction")}</button>
          </div>
        </div>

        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))" }}>
          <HeaderStat label={t("workspace.detected")} value={fmtDateTime(event.started_at, locale)} />
          <HeaderStat label={t("workspace.duration")} value={fmtDuration(event.duration_s)} />
          <HeaderStat label={t("workspace.peakRate")} value={fmtKgH(event.peak_emission_rate_kg_h)} />
          <HeaderStat label={t("workspace.totalMass")} value={`${fmtNum(event.total_mass_kg, 3)} kg`} sub={`±${fmtNum(event.uncertainty_pct, 0)}%`} />
          <HeaderStat label={t("common.confidence")} value={fmtPct(event.attribution_confidence)} />
          <HeaderStat label={t("workspace.gasLoss")} value={fmtOmr(event.gas_value_lost_omr)} />
          <HeaderStat label={t("workspace.co2e")} value={`${fmtNum(event.environmental?.co2e_t_100yr, 4)} t`} />
        </div>
      </div>

      {/* Charts */}
      <div className="panel mb-5">
        <div className="panel-title mb-4">{t("workspace.timeline")}</div>
        {timeseries && <EventCharts data={timeseries} />}
      </div>

      <div className="grid gap-5 mb-5" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        <div className="flex flex-col gap-5">
          {/* Probable source */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.probableSource")}</div>
            {leader && (
              <div className="rounded-xl p-4 mb-3" style={{ background: "var(--red-bg)" }}>
                <div className="flex items-center justify-between mb-2">
                  <span style={{ fontSize: 18, fontWeight: 700 }}>{leader.tag} — {leader.name}</span>
                  <span style={{ fontSize: 20, fontWeight: 700, color: "var(--red)" }}>{leader.score_pct}%</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("workspace.estimateDisclaimer")}</div>
              </div>
            )}
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{t("workspace.confidenceBreakdown")}</div>
            {leader?.factors.map((f) => (
              <FactorBar key={f.name} name={f.name} value={f.value} detail={f.detail} />
            ))}
          </div>

          {/* Alternative candidates */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.alternativeCandidates")}</div>
            <div className="flex flex-col gap-2">
              {candidates.slice(1).map((c) => (
                <div key={c.equipment_id} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "var(--cream)" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{c.tag} — {c.name}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-muted)" }}>{c.score_pct}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* AI Summary */}
          <div className="panel">
            <div className="flex items-center justify-between mb-3">
              <span className="panel-title">{t("workspace.aiSummary")}</span>
              {!investigation && (
                <button className="btn-primary" onClick={runInvestigation} disabled={investigating}>
                  {investigating ? t("workspace.investigating") : t("workspace.runInvestigation")}
                </button>
              )}
            </div>
            {investigation ? (
              <div>
                <p style={{ fontSize: 13.5, lineHeight: 1.7, color: "var(--text-dark)" }}>{investigation.report.summary}</p>
                {investigation.report.uncertainties?.length > 0 && (
                  <div className="mt-3">
                    <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 4 }}>Uncertainties</div>
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.7 }}>
                      {investigation.report.uncertainties.map((u, i) => <li key={i}>{u}</li>)}
                    </ul>
                  </div>
                )}
                <div className="mt-3 flex items-center gap-2" style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                  <span className="tag-simulated" style={{ background: "var(--grey-bg)", color: "var(--grey)" }}>
                    provider: {investigation.provider}
                  </span>
                  <span>{investigation.tool_calls?.length ?? 0} evidence checks · {investigation.duration_ms}ms</span>
                </div>
                {investigation.report.authority_note && (
                  <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 8, fontStyle: "italic" }}>
                    {investigation.report.authority_note}
                  </p>
                )}
              </div>
            ) : (
              <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No investigation run yet.</p>
            )}

            {investigation && investigation.tool_calls?.length > 0 && (
              <details className="mt-3">
                <summary style={{ fontSize: 12, fontWeight: 600, color: "var(--green)", cursor: "pointer" }}>
                  {t("workspace.activityFeed")}
                </summary>
                <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.9 }}>
                  {investigation.tool_calls.map((tc, i) => <li key={i}><code>{tc.tool}()</code></li>)}
                </ul>
              </details>
            )}
          </div>

          {/* Recommended action */}
          {investigation && (
            <div className="panel">
              <div className="panel-title mb-3">{t("workspace.recommendedAction")}</div>
              <div style={{ fontSize: 13.5, fontWeight: 600 }}>{investigation.report.recommended_inspection}</div>
              <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>
                {t("takeAction.discipline")}: {investigation.report.discipline}
              </div>
              {!workOrder && (
                <button className="btn-danger mt-3" onClick={() => setShowAction(true)}>{t("common.takeAction")}</button>
              )}
              {workOrder && (
                <div className="mt-3 rounded-lg p-3" style={{ background: "var(--normal-bg)" }}>
                  <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--normal-green)" }}>
                    {workOrder.id} — {workOrder.status}
                  </span>
                  <Link href={`/${locale}/work-orders`} style={{ fontSize: 12, color: "var(--green)", marginLeft: 10 }}>
                    {t("common.viewDetails")} →
                  </Link>
                </div>
              )}
            </div>
          )}

          {/* Verification */}
          {verificationLatest && (
            <VerificationPanel v={verificationLatest} t={t} />
          )}
        </div>

        <div className="flex flex-col gap-5">
          {/* Evidence used */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.evidenceUsed")}</div>
            {evidence.filter((e) => e.kind !== "alternative").map((e, i) => (
              <div className="evidence-item" key={i}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", marginTop: 6, flexShrink: 0 }} />
                <span style={{ fontSize: 12.5, color: "var(--text-dark)", lineHeight: 1.6 }}>{e.summary}</span>
              </div>
            ))}
          </div>

          {/* Data quality */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.dataQuality")}</div>
            <FactorBar name={t("common.confidence")} value={event.detection_confidence || 0} color="var(--blue)" />
            <FactorBar name="Attribution confidence" value={event.attribution_confidence || 0} color="var(--orange)" />
            <FactorBar name={t("workspace.dataQuality")} value={event.data_quality || 0} color="var(--normal-green)" />
          </div>

          {/* Financial & environmental */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.financialImpact")}</div>
            <MetricRow label="Gas value lost" value={fmtOmr(event.financial?.gas_value_lost_omr)} />
            <MetricRow label="Daily (projected)" value={fmtOmr(event.financial?.daily_loss_omr)} />
            <MetricRow label="Annual (projected)" value={fmtOmr(event.financial?.annual_loss_omr)} />
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>{event.financial?.projection_note}</p>
          </div>

          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.environmentalImpact")}</div>
            <MetricRow label="CH4 released" value={`${fmtNum(event.environmental?.ch4_kg, 4)} kg`} />
            <MetricRow label="CO2e (100yr GWP)" value={`${fmtNum(event.environmental?.co2e_t_100yr, 4)} t`} />
            <MetricRow label="CO2e (20yr GWP)" value={`${fmtNum(event.environmental?.co2e_t_20yr, 4)} t`} />
          </div>

          {/* Assumptions */}
          <div className="panel">
            <div className="panel-title mb-3">{t("workspace.assumptions")}</div>
            <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.8 }}>
              <div><strong>Model:</strong> {event.quantification_assumptions?.model}</div>
              <div><strong>Status:</strong> {event.quantification_assumptions?.validation_status}</div>
              <div><strong>Release height:</strong> {event.quantification_assumptions?.release_height_assumed_m} m</div>
              <div><strong>Stability basis:</strong> {event.quantification_assumptions?.stability_derived_from}</div>
            </div>
          </div>

          {/* Similar events */}
          {similar.length > 0 && (
            <div className="panel">
              <div className="panel-title mb-3">{t("workspace.similarEvents")}</div>
              {similar.map((s) => (
                <Link key={s.id} href={`/${locale}/events/${s.id}`} className="flex items-center justify-between py-1.5" style={{ fontSize: 12.5 }}>
                  <span style={{ color: "var(--green)", fontWeight: 600 }}>{s.id}</span>
                  <span style={{ color: "var(--text-muted)" }}>{fmtKgH(s.peak_emission_rate_kg_h)}</span>
                </Link>
              ))}
            </div>
          )}

          <Copilot eventId={event.id} />
        </div>
      </div>

      {showAction && event && (
        <TakeActionModal
          event={event}
          investigation={investigation}
          onClose={() => setShowAction(false)}
          onCreated={(wo) => { setWorkOrder(wo); setShowAction(false); }}
        />
      )}

      {reportUrl && (
        <div className="fixed bottom-6 right-6 card p-4" style={{ zIndex: 40 }}>
          <div style={{ fontSize: 13, marginBottom: 6 }}>Report generated.</div>
          <Link href={reportUrl} className="btn-primary">{t("common.viewDetails")}</Link>
        </div>
      )}
    </div>
  );
}

function HeaderStat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-dark)" }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{value}</span>
    </div>
  );
}

function VerificationPanel({ v, t }: { v: Verification; t: any }) {
  const verified = v.outcome === "REPAIR VERIFIED";
  const series = v.comparison_series;
  const chartData = series
    ? mergeCompare(series.pre, series.post)
    : [];

  return (
    <div className="panel">
      <div className="panel-title mb-3">Repair Verification</div>
      <div
        className="rounded-lg p-3 mb-3 flex items-center gap-2"
        style={{ background: verified ? "var(--normal-bg)" : "var(--red-bg)" }}
      >
        <span style={{ fontSize: 14, fontWeight: 700, color: verified ? "var(--normal-green)" : "var(--red)" }}>
          {v.outcome}
        </span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>({fmtNum(v.reduction_pct, 0)}% reduction)</span>
      </div>
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={chartData}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="i" fontSize={10} stroke="var(--text-muted)" />
            <YAxis fontSize={10} stroke="var(--text-muted)" width={30} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="pre" name="Pre-repair" stroke="var(--red)" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="post" name="Post-repair" stroke="var(--normal-green)" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      )}
      {verified && (
        <div className="grid grid-cols-2 gap-2 mt-3">
          <MetricRow label="CH4 avoided/yr" value={`${fmtNum(v.ch4_avoided_kg_year, 1)} kg`} />
          <MetricRow label="Value retained/yr" value={fmtOmr(v.gas_value_retained_omr_year)} />
        </div>
      )}
    </div>
  );
}

function mergeCompare(pre: { t: string; ppm: number }[], post: { t: string; ppm: number }[]) {
  const n = Math.max(pre.length, post.length);
  const out: { i: number; pre?: number; post?: number }[] = [];
  for (let i = 0; i < n; i++) {
    out.push({ i, pre: pre[i]?.ppm, post: post[i]?.ppm });
  }
  return out;
}
