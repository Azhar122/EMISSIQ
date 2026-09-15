"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from "recharts";
import { Timeseries } from "@/lib/api";
import { fmtTime } from "@/lib/format";

const SENSOR_COLORS: Record<string, string> = {
  S1: "#8C8C84", S2: "#8C8C84", S3: "#C4453F", S4: "#C97A2E", S5: "#8C8C84", S6: "#8C8C84",
};

function MarkerLines({ markers }: { markers: Timeseries["markers"] }) {
  return (
    <>
      {markers.map((m) => (
        <ReferenceLine
          key={m.label}
          x={m.t}
          stroke="var(--umber)"
          strokeDasharray="3 3"
          label={{ value: m.label, fontSize: 10, fill: "var(--umber)", position: "top" }}
        />
      ))}
    </>
  );
}

export function EventCharts({ data }: { data: Timeseries }) {
  const ch4Series = buildMergedSeries(data.ch4_by_sensor);
  const sensorTags = Object.keys(data.ch4_by_sensor);

  const processSeries = data.process.map((p) => ({ t: p.t, pressure_barg: p.pressure_barg, flow_kg_h: p.flow_kg_h }));
  const windSeries = data.wind.map((w) => ({ t: w.t, wind_speed_ms: w.wind_speed_ms }));

  const tickFormatter = (t: string) => fmtTime(t);

  return (
    <div className="grid gap-5" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <ChartBox title="CH4 Concentration (ppm)">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={ch4Series}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" tickFormatter={tickFormatter} fontSize={10} stroke="var(--text-muted)" minTickGap={40} />
            <YAxis fontSize={10} stroke="var(--text-muted)" width={36} />
            <Tooltip labelFormatter={tickFormatter} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <MarkerLines markers={data.markers} />
            {sensorTags.map((tag) => (
              <Line key={tag} type="monotone" dataKey={tag} stroke={SENSOR_COLORS[tag] || "#33689C"} dot={false} strokeWidth={tag === "S3" || tag === "S4" ? 2 : 1} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </ChartBox>

      <ChartBox title="Discharge Pressure (barg)">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={processSeries}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" tickFormatter={tickFormatter} fontSize={10} stroke="var(--text-muted)" minTickGap={40} />
            <YAxis fontSize={10} stroke="var(--text-muted)" width={36} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={tickFormatter} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <MarkerLines markers={data.markers} />
            <Line type="monotone" dataKey="pressure_barg" stroke="var(--blue)" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </ChartBox>

      <ChartBox title="Flow (kg/h)">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={processSeries}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" tickFormatter={tickFormatter} fontSize={10} stroke="var(--text-muted)" minTickGap={40} />
            <YAxis fontSize={10} stroke="var(--text-muted)" width={36} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={tickFormatter} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <MarkerLines markers={data.markers} />
            <Line type="monotone" dataKey="flow_kg_h" stroke="var(--normal-green)" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </ChartBox>

      <ChartBox title="Wind Speed (m/s)">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={windSeries}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" tickFormatter={tickFormatter} fontSize={10} stroke="var(--text-muted)" minTickGap={40} />
            <YAxis fontSize={10} stroke="var(--text-muted)" width={36} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={tickFormatter} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <MarkerLines markers={data.markers} />
            <Line type="monotone" dataKey="wind_speed_ms" stroke="var(--amber)" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </ChartBox>
    </div>
  );
}

function ChartBox({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-dark)", marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function buildMergedSeries(bySensor: Timeseries["ch4_by_sensor"]) {
  const timestamps = new Set<string>();
  Object.values(bySensor).forEach((series) => series.forEach((p) => timestamps.add(p.t)));
  const sorted = Array.from(timestamps).sort();
  const index: Record<string, Record<string, number>> = {};
  for (const [tag, series] of Object.entries(bySensor)) {
    for (const p of series) {
      index[p.t] = index[p.t] || {};
      index[p.t][tag] = p.ch4_ppm;
    }
  }
  return sorted.map((t) => ({ t, ...index[t] }));
}
