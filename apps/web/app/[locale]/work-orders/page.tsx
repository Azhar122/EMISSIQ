"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { api, WorkOrder } from "@/lib/api";
import { fmtDateTime, priorityBadgeClass } from "@/lib/format";
import { useDemo } from "@/components/DemoProvider";

const STATUS_ORDER = ["Open", "Assigned", "In Progress", "Repair Completed", "Verification", "Closed"];
const STATUS_COLOR: Record<string, string> = {
  Open: "badge-info", Assigned: "badge-info", "In Progress": "badge-medium",
  "Repair Completed": "badge-high", Verification: "badge-high", Closed: "badge-normal",
};

export default function WorkOrdersPage() {
  const t = useTranslations();
  const locale = useLocale();
  const demo = useDemo();
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    const rows = await api.get<WorkOrder[]>("/api/workorders");
    setOrders(rows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)));
  }

  useEffect(() => { load(); }, [demo.version]);

  async function advance(wo: WorkOrder) {
    const idx = STATUS_ORDER.indexOf(wo.status);
    const next = STATUS_ORDER[idx + 1];
    if (!next) return;
    setBusy(wo.id);
    try {
      if (next === "Repair Completed") {
        await api.post(`/api/workorders/${wo.id}/complete-repair`);
      } else {
        await api.patch(`/api/workorders/${wo.id}`, { status: next });
      }
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="page-header-row mb-6 flex items-start justify-between">
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("workOrders.title")}</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("workOrders.subtitle")}</p>
        </div>
      </div>

      <div className="table-panel panel" style={{ paddingBottom: 8 }}>
        <table>
          <thead>
            <tr>
              <th>{t("workOrders.columnId")}</th>
              <th>{t("workOrders.columnEvent")}</th>
              <th>{t("workOrders.columnAssignee")}</th>
              <th>{t("workOrders.columnPriority")}</th>
              <th>{t("workOrders.columnStatus")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((wo) => {
              const idx = STATUS_ORDER.indexOf(wo.status);
              const next = STATUS_ORDER[idx + 1];
              return (
                <tr key={wo.id}>
                  <td style={{ fontWeight: 700 }}>{wo.id}</td>
                  <td>
                    {wo.event_id ? (
                      <Link href={`/${locale}/events/${wo.event_id}`} style={{ color: "var(--green)" }}>{wo.event_id}</Link>
                    ) : "—"}
                  </td>
                  <td>{wo.assignee || "Unassigned"}</td>
                  <td><span className={`badge ${priorityBadgeClass(wo.priority)}`}>{wo.priority}</span></td>
                  <td><span className={`badge ${STATUS_COLOR[wo.status] || "badge-grey"}`}>{wo.status}</span></td>
                  <td>
                    {next && (
                      <button
                        className="btn-secondary"
                        style={{ padding: "6px 12px", fontSize: 12 }}
                        disabled={busy === wo.id}
                        onClick={() => advance(wo)}
                      >
                        {busy === wo.id ? "…" : `→ ${next}`}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {orders.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>No work orders yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
