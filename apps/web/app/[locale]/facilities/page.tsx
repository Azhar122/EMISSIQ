"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, Facility } from "@/lib/api";
import { useDemo } from "@/components/DemoProvider";

const STATUS_COLOR: Record<string, string> = { Attention: "badge-critical", Monitoring: "badge-medium", Normal: "badge-normal" };

export default function FacilitiesPage() {
  const t = useTranslations();
  const demo = useDemo();
  const [facilities, setFacilities] = useState<Facility[]>([]);

  useEffect(() => {
    api.get<Facility[]>("/api/facilities").then(setFacilities);
  }, [demo.version]);

  return (
    <div>
      <div className="page-header mb-6">
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("facilities.title")}</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("facilities.subtitle")}</p>
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
        {facilities.map((f) => (
          <div key={f.id} className="panel">
            <div className="flex items-center justify-between mb-2">
              <span style={{ fontSize: 15.5, fontWeight: 700 }}>{f.name}</span>
              <span className={`badge ${STATUS_COLOR[f.status] || "badge-grey"}`}>{f.status}</span>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 12 }}>{f.region} · {f.block}</div>
            <div className="flex gap-4">
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("facilities.equipment")}</div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{f.equipment_count}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t("facilities.openEvents")}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: f.open_events > 0 ? "var(--red)" : "var(--text-dark)" }}>
                  {f.open_events}
                </div>
              </div>
            </div>
            {f.is_simulated && <div className="tag-simulated mt-3">{t("common.simulatedData")}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
