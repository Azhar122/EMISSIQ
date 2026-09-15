"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { api, EventDetail, AIInvestigation, WorkOrder } from "@/lib/api";
import { fmtOmr, fmtKgH } from "@/lib/format";

const TECHNICIANS = ["Salim Al-Balushi", "Fatma Al-Habsi", "Hamed Al-Rashdi", "Yusra Al-Kindi", "Nasser Al-Amri"];

export function TakeActionModal({
  event,
  investigation,
  onClose,
  onCreated,
}: {
  event: EventDetail;
  investigation: AIInvestigation | null;
  onClose: () => void;
  onCreated: (wo: WorkOrder) => void;
}) {
  const t = useTranslations();
  const [assignee, setAssignee] = useState(TECHNICIANS[0]);
  const [creating, setCreating] = useState(false);

  const report = investigation?.report;
  const inspection = report?.recommended_inspection || "General leak survey";
  const discipline = report?.discipline || "Mechanical";
  const evidence = report?.key_evidence || [];

  async function createWorkOrder() {
    setCreating(true);
    try {
      const wo = await api.post<WorkOrder>("/api/workorders", {
        event_id: event.id,
        facility_id: event.facility_id,
        equipment_id: null,
        title: `${inspection} — ${event.equipment_tag ?? "attributed asset"}`,
        description: report?.summary || "",
        discipline,
        priority: event.priority || "Medium",
        assignee,
        ai_drafted: true,
      });
      onCreated(wo);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(36,53,44,0.45)" }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ width: "min(560px, 92vw)", maxHeight: "88vh", overflowY: "auto", padding: 26 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, color: "var(--green)" }}>{t("takeAction.title")}</h2>
          <button onClick={onClose} style={{ color: "var(--text-muted)", fontSize: 20, lineHeight: 1 }}>×</button>
        </div>

        <Field label={t("takeAction.recommendedInspection")} value={inspection} />
        <Field label={t("takeAction.discipline")} value={discipline} />
        <Field
          label={t("takeAction.reason")}
          value={report?.summary || `${event.severity} severity event attributed to ${event.equipment_tag}.`}
        />

        <div className="grid grid-cols-2 gap-3 my-4">
          <Metric label={t("takeAction.ongoingLoss")} value={fmtKgH(event.peak_emission_rate_kg_h)} />
          <Metric label={t("takeAction.financialConsequence")} value={fmtOmr(event.financial?.annual_loss_omr)} sub="projected/yr" />
        </div>

        {evidence.length > 0 && (
          <div className="mb-4">
            <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text-dark)", marginBottom: 6 }}>
              {t("takeAction.supportingEvidence")}
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.7 }}>
              {evidence.slice(0, 4).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}

        <div className="mb-5">
          <label style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text-dark)", display: "block", marginBottom: 6 }}>
            {t("takeAction.assignTechnician")}
          </label>
          <select className="filter-select" style={{ width: "100%" }} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            {TECHNICIANS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        <div className="flex gap-2 justify-end">
          <button className="btn-secondary" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn-primary" onClick={createWorkOrder} disabled={creating}>
            {creating ? t("takeAction.creating") : t("takeAction.createWorkOrder")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-3">
      <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13.5, color: "var(--text-dark)" }}>{value}</div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg p-3" style={{ background: "var(--cream)" }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}
