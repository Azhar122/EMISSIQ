"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { api, EventSummary } from "@/lib/api";
import { fmtNum, fmtOmr, priorityBadgeClass } from "@/lib/format";
import { useDemo } from "@/components/DemoProvider";
import { FactorBar } from "@/components/FactorBar";

const ORDER = ["Critical", "High", "Medium", "Low"];

export default function PriorityCenterPage() {
  const t = useTranslations();
  const locale = useLocale();
  const demo = useDemo();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [factorsById, setFactorsById] = useState<Record<string, any[]>>({});

  useEffect(() => {
    api.get<EventSummary[]>("/api/events?limit=100").then((rows) => {
      const active = rows.filter((r) => r.status !== "Closed");
      const sorted = active.sort((a, b) => ORDER.indexOf(a.priority || "Low") - ORDER.indexOf(b.priority || "Low"));
      setEvents(sorted);
      sorted.slice(0, 6).forEach((e) => {
        api.get<{ factors: any[] }>(`/api/events/${e.id}/priority`).then((d) => {
          setFactorsById((prev) => ({ ...prev, [e.id]: d.factors }));
        }).catch(() => {});
      });
    });
  }, [demo.version]);

  return (
    <div>
      <div className="page-header mb-6">
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("priority.title")}</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("priority.subtitle")}</p>
      </div>

      <div className="flex flex-col gap-3.5">
        {events.map((e, i) => (
          <div key={e.id} className="panel flex items-center gap-4">
            <div
              className="flex items-center justify-center rounded-full flex-shrink-0"
              style={{ width: 34, height: 34, background: "var(--cream)", fontWeight: 700, color: "var(--green)" }}
            >
              {i + 1}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="flex items-center gap-2 mb-1">
                <Link href={`/${locale}/events/${e.id}`} style={{ fontSize: 15, fontWeight: 700, color: "var(--text-dark)" }}>
                  {e.id}
                </Link>
                <span className={`badge ${priorityBadgeClass(e.priority)}`}>{e.priority}</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                {e.facility_name} — {e.equipment_name || "Unattributed"}
              </div>
              {factorsById[e.id] && (
                <div className="mt-2 grid gap-1.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
                  {factorsById[e.id].slice(0, 4).map((f) => (
                    <FactorBar key={f.name} name={f.name} value={f.value} />
                  ))}
                </div>
              )}
            </div>
            <div className="text-right flex-shrink-0">
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("priority.gasValueLost")}</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{fmtOmr(e.gas_value_lost_omr)}</div>
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <div className="panel" style={{ color: "var(--text-muted)", textAlign: "center" }}>No active events.</div>
        )}
      </div>
    </div>
  );
}
