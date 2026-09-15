"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, DataSource } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useDemo } from "@/components/DemoProvider";

const STATUS_COLOR: Record<string, string> = { Connected: "badge-normal", Degraded: "badge-medium", Disconnected: "badge-grey" };

export default function DataSourcesPage() {
  const t = useTranslations();
  const demo = useDemo();
  const [sources, setSources] = useState<DataSource[]>([]);

  useEffect(() => {
    api.get<DataSource[]>("/api/datasources").then(setSources);
  }, [demo.version]);

  return (
    <div>
      <div className="page-header mb-6">
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--green)" }}>{t("dataSources.title")}</h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>{t("dataSources.subtitle")}</p>
      </div>

      <div className="flex flex-col gap-3">
        {sources.map((s) => (
          <div key={s.id} className="panel flex items-center gap-5 flex-wrap">
            <div style={{ flex: "1 1 220px" }}>
              <div className="flex items-center gap-2 mb-1">
                <span style={{ fontSize: 14.5, fontWeight: 700 }}>{s.name}</span>
                <span className={`badge ${STATUS_COLOR[s.status] || "badge-grey"}`}>{s.status}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{s.type}</div>
              <div className="tag-simulated mt-1.5">{s.label}</div>
            </div>
            <Stat label={t("dataSources.lastPacket")} value={fmtDateTime(s.last_packet)} />
            <Stat label={t("dataSources.latency")} value={s.latency_s !== null && s.latency_s !== undefined ? `${s.latency_s.toFixed(0)}s` : "—"} />
            <Stat label={t("dataSources.dataQuality")} value={`${Math.round((s.data_quality || 0) * 100)}%`} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 100 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</div>
      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{value}</div>
    </div>
  );
}
