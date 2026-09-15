"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { fmtNum, fmtOmr, fmtDateTime } from "@/lib/format";

export default function ReportPage() {
  const t = useTranslations();
  const params = useParams<{ reportId: string }>();
  const [snapshot, setSnapshot] = useState<any>(null);

  useEffect(() => {
    api.get<{ snapshot: any }>(`/api/reports/${params.reportId}`).then((r) => setSnapshot(r.snapshot));
  }, [params.reportId]);

  if (!snapshot) return <div style={{ color: "var(--text-muted)" }}>{t("common.loading")}</div>;

  return (
    <div className="card p-8 mx-auto" style={{ maxWidth: 820 }} id="printable-report">
      <div className="flex items-center justify-between border-b pb-4 mb-5" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center gap-4">
          <img src="/logo-mark.png" alt="EMISSIQ" style={{ height: 52, width: "auto" }} />
          <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "var(--green)" }}>{t("report.title")}</h1>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{snapshot.identification.event_id}</div>
          </div>
        </div>
        <span className="tag-simulated">{snapshot.data_note}</span>
      </div>

      <Section title={t("report.identification")}>
        <Row label="Facility" value={`${snapshot.identification.facility} (${snapshot.identification.region}, ${snapshot.identification.block})`} />
        <Row label="Detected" value={fmtDateTime(snapshot.timestamps.detected_at)} />
        <Row label="Peak" value={fmtDateTime(snapshot.timestamps.peak_at)} />
        <Row label="Ended" value={fmtDateTime(snapshot.timestamps.ended_at)} />
        <Row label="Duration" value={`${fmtNum(snapshot.timestamps.duration_s, 0)} s`} />
      </Section>

      <Section title="Probable Source">
        <Row label="Equipment" value={`${snapshot.probable_source.equipment_name} (${snapshot.probable_source.equipment_tag})`} />
        <Row label="Attribution confidence" value={fmtNum((snapshot.probable_source.attribution_confidence || 0) * 100, 1) + "%"} />
        <p style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic" }}>{snapshot.probable_source.caveat}</p>
      </Section>

      <Section title="Candidate Sources">
        {snapshot.candidate_sources.map((c: any) => (
          <Row key={c.tag} label={c.tag} value={`${c.score_pct}%`} />
        ))}
      </Section>

      <Section title="Sensor & Process Evidence">
        <ul style={{ fontSize: 12.5, lineHeight: 1.8, paddingLeft: 18 }}>
          {snapshot.sensor_evidence.map((e: any, i: number) => <li key={i}>{e.summary}</li>)}
        </ul>
      </Section>

      <Section title="Emission Estimate">
        <Row label="Peak rate" value={`${fmtNum(snapshot.emission_estimate.peak_rate_kg_ch4_h, 2)} kg CH4/h`} />
        <Row label="Total mass" value={`${fmtNum(snapshot.emission_estimate.total_mass_kg_ch4, 4)} kg CH4`} />
        <Row label="Uncertainty" value={`±${fmtNum(snapshot.emission_estimate.uncertainty_pct, 0)}%`} />
      </Section>

      <Section title="Financial & Environmental Impact">
        <Row label="Gas value lost" value={fmtOmr(snapshot.financial_impact?.gas_value_lost_omr)} />
        <Row label="Annual projection" value={fmtOmr(snapshot.financial_impact?.annual_loss_omr)} />
        <Row label="CO2e (100yr)" value={`${fmtNum(snapshot.environmental_impact?.co2e_t_100yr, 4)} t`} />
      </Section>

      {snapshot.ai_investigation && (
        <Section title="AI Investigation Summary">
          <p style={{ fontSize: 12.5, lineHeight: 1.7 }}>{snapshot.ai_investigation.summary}</p>
          <Row label="Recommended inspection" value={snapshot.ai_investigation.recommended_inspection} />
          <Row label="Discipline" value={snapshot.ai_investigation.discipline} />
        </Section>
      )}

      {snapshot.work_order && (
        <Section title="Work Order">
          <Row label="ID" value={snapshot.work_order.id} />
          <Row label="Status" value={snapshot.work_order.status} />
          <Row label="Assignee" value={snapshot.work_order.assignee} />
        </Section>
      )}

      {snapshot.repair_and_verification && (
        <Section title="Repair Verification">
          <Row label="Outcome" value={snapshot.repair_and_verification.outcome} />
          <Row label="CH4 avoided/yr" value={`${fmtNum(snapshot.repair_and_verification.ch4_avoided_kg_year, 1)} kg`} />
          <Row label="Value retained/yr" value={fmtOmr(snapshot.repair_and_verification.gas_value_retained_omr_year)} />
        </Section>
      )}

      <Section title={t("report.auditTrail")}>
        <ul style={{ fontSize: 12, lineHeight: 1.8, paddingLeft: 18, color: "var(--text-muted)" }}>
          {(snapshot.audit_trail || []).map((a: any, i: number) => (
            <li key={i}>{fmtDateTime(a.at)} — {a.actor}: {a.action}</li>
          ))}
        </ul>
      </Section>

      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 20 }}>
        {t("report.generated")}: {fmtDateTime(snapshot.generated_at)}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--green)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between py-1" style={{ fontSize: 13, borderBottom: "1px dotted var(--border)" }}>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{value ?? "—"}</span>
    </div>
  );
}
