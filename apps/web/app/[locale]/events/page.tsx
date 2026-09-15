"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { api, EventSummary } from "@/lib/api";
import { fmtNum, fmtDateTime, severityBadgeClass, statusBadgeClass } from "@/lib/format";
import { useDemo } from "@/components/DemoProvider";

export default function EventsPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const demo = useDemo();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.get<EventSummary[]>("/api/events?limit=100").then(setEvents).catch(() => {});
  }, [demo.version]);

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (severity && e.severity !== severity) return false;
      if (status && e.status !== status) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!e.id.toLowerCase().includes(q) && !(e.equipment_name || "").toLowerCase().includes(q) && !e.facility_name.toLowerCase().includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [events, search, severity, status]);

  const severities = Array.from(new Set(events.map((e) => e.severity)));
  const statuses = Array.from(new Set(events.map((e) => e.status)));

  return (
    <div>
      <div className="page-header mb-6">
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("events.title")}</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("events.subtitle")}</p>
      </div>

      <div className="flex gap-2.5 mb-4 flex-wrap items-center">
        <input
          className="filter-input"
          style={{ flex: "1 1 220px", minWidth: 180 }}
          placeholder={t("events.search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="filter-select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">{t("events.allSeverities")}</option>
          {severities.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t("events.allStatuses")}</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="table-panel panel" style={{ paddingBottom: 8 }}>
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
            {filtered.map((e) => (
              <tr key={e.id} className="clickable" onClick={() => router.push(`/${locale}/events/${e.id}`)}>
                <td style={{ fontWeight: 700 }}>{e.id}</td>
                <td>{e.equipment_name ? `${e.equipment_name}, ${e.facility_name}` : e.facility_name}</td>
                <td>{fmtNum(e.peak_emission_rate_kg_h, 1)} kg/hr</td>
                <td><span className={`badge ${severityBadgeClass(e.severity)}`}>{e.severity}</span></td>
                <td><span className={`badge ${statusBadgeClass(e.status)}`}>{e.status}</span></td>
                <td>{fmtDateTime(e.started_at, locale)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>No events match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
