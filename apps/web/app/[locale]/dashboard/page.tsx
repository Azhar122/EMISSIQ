"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { api, AnalyticsSummary, EventSummary } from "@/lib/api";
import { fmtDuration, fmtNum, fmtOmr, fmtDateTime, severityBadgeClass, statusBadgeClass } from "@/lib/format";
import { StatCard } from "@/components/StatCard";
import { useDemo } from "@/components/DemoProvider";
import { MiniSchematic } from "@/components/MiniSchematic";

export default function DashboardPage() {
  const t = useTranslations();
  const locale = useLocale();
  const demo = useDemo();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [topEvent, setTopEvent] = useState<EventSummary | null>(null);

  useEffect(() => {
    api.get<AnalyticsSummary>("/api/analytics/summary?days=1").then(setSummary).catch(() => {});
    api.get<EventSummary[]>("/api/events?limit=8").then((rows) => {
      setEvents(rows);
      const active = rows.find((e) => e.status !== "Closed" && (e.priority === "Critical" || e.priority === "High")) || rows[0] || null;
      setTopEvent(active);
    }).catch(() => {});
  }, [demo.version]);

  const activeCount = events.filter((e) => e.status !== "Closed").length;

  return (
    <div>
      <div className="flex items-start gap-3 mb-6">
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: "var(--green)" }}>
            {t("dashboard.greeting")}
          </h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14.5 }}>
            {t("dashboard.subtitle")}
          </p>
        </div>
      </div>

      <div className="flex gap-4 mb-6 flex-wrap">
        <StatCard
          label={t("dashboard.statMethaneDetected")}
          value={summary ? `${fmtNum(summary.methane_detected_kg, 2)} kg` : "…"}
          caption={t("common.simulatedData")}
          captionColor="var(--text-muted)"
        />
        <StatCard
          label={t("dashboard.statActiveEvents")}
          value={String(activeCount)}
          caption={activeCount > 0 ? "Requires attention" : "All clear"}
          captionColor={activeCount > 0 ? "var(--red)" : "var(--normal-green)"}
        />
        <StatCard
          label={t("dashboard.statGasValueLost")}
          value={summary ? fmtOmr(summary.financial_loss_detected_omr) : "…"}
          caption={t("common.projection")}
          captionColor="var(--text-muted)"
        />
        <StatCard
          label={t("dashboard.statAvgResolution")}
          value={summary ? `${fmtNum(summary.average_resolution_time_hours, 1)}h` : "…"}
        />
      </div>

      <div className="flex gap-4 mb-6 items-stretch flex-wrap lg:flex-nowrap">
        <div className="panel" style={{ flex: "0 0 34%", minWidth: 320 }}>
          <div className="flex items-center justify-between mb-4">
            <span className="panel-title">{t("dashboard.topPriority")}</span>
          </div>
          {topEvent ? (
            <div className="rounded-xl p-4" style={{ background: "var(--red-bg)", border: "1px solid #F3CFCB" }}>
              <div className="flex items-center justify-between mb-3">
                <span className={`badge ${severityBadgeClass(topEvent.severity)}`}>{topEvent.severity}</span>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{fmtDateTime(topEvent.started_at, locale)}</span>
              </div>
              <div style={{ fontSize: 19, fontWeight: 700, color: "var(--text-dark)" }}>{topEvent.id}</div>
              <div className="flex items-center gap-1 mb-4" style={{ fontSize: 13, color: "var(--text-muted)" }}>
                {topEvent.equipment_name}, {topEvent.facility_name}
              </div>
              <div className="flex gap-2.5 bg-white rounded-lg p-3.5 mb-4">
                <div className="flex-1">
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Peak rate</div>
                  <div style={{ fontSize: 17, fontWeight: 700 }}>{fmtNum(topEvent.peak_emission_rate_kg_h, 1)} kg/h</div>
                </div>
                <div className="flex-1">
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Gas value lost</div>
                  <div style={{ fontSize: 17, fontWeight: 700 }}>{fmtOmr(topEvent.gas_value_lost_omr)}</div>
                </div>
              </div>
              <Link href={`/${locale}/events/${topEvent.id}`} className="btn-danger" style={{ width: "100%", justifyContent: "center" }}>
                {t("common.takeAction")}
              </Link>
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontSize: 13.5 }}>No active priority events.</div>
          )}
        </div>

        <div className="panel flex-1" style={{ minWidth: 0 }}>
          <div className="flex items-center justify-between mb-4">
            <span className="panel-title">{t("dashboard.liveMonitoring")}</span>
            <Link href={`/${locale}/live-monitoring`} style={{ fontSize: 13, fontWeight: 600, color: "var(--green)" }}>
              {t("common.viewDetails")} →
            </Link>
          </div>
          <MiniSchematic />
        </div>
      </div>

      <div className="table-panel panel" style={{ paddingBottom: 8 }}>
        <div className="flex items-center justify-between mb-4">
          <span className="panel-title">{t("dashboard.recentEvents")}</span>
          <Link href={`/${locale}/events`} style={{ fontSize: 13, fontWeight: 600, color: "var(--green)" }}>
            {t("common.viewDetails")} →
          </Link>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t("events.columnId")}</th>
              <th>{t("events.columnLocation")}</th>
              <th>{t("events.columnAmount")}</th>
              <th>{t("events.columnSeverity")}</th>
              <th>{t("events.columnStatus")}</th>
              <th>{t("events.columnDetected")}</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} className="clickable" onClick={() => (window.location.href = `/${locale}/events/${e.id}`)}>
                <td className="cell-strong" style={{ fontWeight: 700 }}>{e.id}</td>
                <td>{e.equipment_name ? `${e.equipment_name}, ${e.facility_name}` : e.facility_name}</td>
                <td>{fmtNum(e.peak_emission_rate_kg_h, 1)} kg/hr</td>
                <td><span className={`badge ${severityBadgeClass(e.severity)}`}>{e.severity}</span></td>
                <td><span className={`badge ${statusBadgeClass(e.status)}`}>{e.status}</span></td>
                <td>{fmtDateTime(e.started_at, locale)}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>{t("common.loading")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
