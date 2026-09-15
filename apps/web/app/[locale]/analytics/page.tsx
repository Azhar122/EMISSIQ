"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { api, AnalyticsSummary } from "@/lib/api";
import { fmtNum, fmtOmr } from "@/lib/format";
import { useDemo } from "@/components/DemoProvider";

const SEVERITY_COLORS: Record<string, string> = {
  Critical: "#C4453F", High: "#C97A2E", Medium: "#B08A2E", Normal: "#3B7A57",
};

export default function AnalyticsPage() {
  const t = useTranslations();
  const demo = useDemo();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);

  useEffect(() => {
    api.get<AnalyticsSummary>("/api/analytics/summary?days=90").then(setSummary);
  }, [demo.version]);

  if (!summary) return <div style={{ color: "var(--text-muted)" }}>{t("common.loading")}</div>;

  const severityData = Object.entries(summary.events_by_severity).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div className="page-header mb-6">
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("analytics.title")}</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("analytics.subtitle")}</p>
      </div>

      <div className="flex gap-4 mb-5 flex-wrap">
        <KpiCard label={t("analytics.methaneDetected")} value={`${fmtNum(summary.methane_detected_kg, 2)} kg`} />
        <KpiCard label={t("analytics.methaneAvoided")} value={`${fmtNum(summary.methane_avoided_kg_year_projection, 1)} kg`} />
        <KpiCard label={t("analytics.financialLoss")} value={fmtOmr(summary.financial_loss_detected_omr)} />
        <KpiCard label={t("analytics.valueRecovered")} value={fmtOmr(summary.gas_value_recovered_omr_year_projection)} />
      </div>

      <div className="grid gap-5 mb-5" style={{ gridTemplateColumns: "1.6fr 1fr" }}>
        <div className="panel">
          <h3 style={{ margin: "0 0 16px", fontSize: 15.5, fontWeight: 700 }}>{t("analytics.dailyMethane")}</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={summary.daily_methane_detected_kg}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="date" fontSize={10} stroke="var(--text-muted)" />
              <YAxis fontSize={10} stroke="var(--text-muted)" />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="methane_kg" stroke="var(--green)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3 style={{ margin: "0 0 16px", fontSize: 15.5, fontWeight: 700 }}>{t("analytics.bySeverity")}</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={severityData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75}>
                {severityData.map((d) => <Cell key={d.name} fill={SEVERITY_COLORS[d.name] || "#8C8C84"} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="legend-inline flex flex-wrap gap-3 justify-center mt-2">
            {severityData.map((d) => (
              <span key={d.name} className="flex items-center gap-1.5" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                <i className="inline-block rounded-full" style={{ width: 9, height: 9, background: SEVERITY_COLORS[d.name] || "#8C8C84" }} />
                {d.name} ({d.value})
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-5" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="panel">
          <h3 style={{ margin: "0 0 16px", fontSize: 15.5, fontWeight: 700 }}>{t("analytics.byFacility")}</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={summary.facility_comparison} layout="vertical">
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis type="number" fontSize={10} stroke="var(--text-muted)" />
              <YAxis type="category" dataKey="facility_name" fontSize={10} stroke="var(--text-muted)" width={100} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="methane_kg" fill="var(--green)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3 style={{ margin: "0 0 16px", fontSize: 15.5, fontWeight: 700 }}>{t("analytics.recurringEquipment")}</h3>
          <div className="flex flex-col gap-2">
            {summary.recurring_equipment.map((r) => (
              <div key={r.tag} className="flex items-center justify-between rounded-lg px-3 py-2.5" style={{ background: "var(--cream)" }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{r.tag} — {r.name}</span>
                <span className="badge badge-medium">{r.event_count} events</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 16 }}>{summary.note}</p>
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel flex-1" style={{ minWidth: 200 }}>
      <div style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 500, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
