/** Thin fetch wrapper over the EMISSIQ FastAPI backend. No caching games —
 * this is a live operational dashboard, every call is fresh. */

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
};

export function wsUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";
  return `${base}${path}`;
}

// ---------------------------------------------------------------------------
// Shapes (kept loose/partial — this is a prototype reading a stable backend,
// not a codegen'd client).
// ---------------------------------------------------------------------------

export interface Facility {
  id: string;
  name: string;
  name_ar: string;
  region: string;
  block: string;
  lat: number;
  lon: number;
  extent_m: number;
  equipment_count: number;
  open_events: number;
  status: string;
  is_simulated: boolean;
}

export interface FacilityDetail extends Facility {
  equipment: { id: string; tag: string; name: string; type: string; x_m: number; y_m: number; criticality: number; operating_state: string }[];
  sensors: { id: string; tag: string; type: string; x_m: number; y_m: number; status: string; baseline_ppm: number }[];
}

export interface EventSummary {
  id: string;
  facility_id: string;
  facility_name: string;
  equipment_tag: string | null;
  equipment_name: string | null;
  detected_by_sensor: string | null;
  started_at: string;
  peak_at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  peak_emission_rate_kg_h: number | null;
  total_mass_kg: number | null;
  uncertainty_pct: number | null;
  severity: string;
  status: string;
  priority: string | null;
  detection_confidence: number | null;
  attribution_confidence: number | null;
  gas_value_lost_omr: number | null;
  run_phase: string;
  is_simulated: boolean;
}

export interface EventDetail extends EventSummary {
  baseline_ch4_ppm: number | null;
  peak_ch4_ppm: number | null;
  peak_zscore: number | null;
  quantification_assumptions: Record<string, any> | null;
  financial: Record<string, any> | null;
  environmental: Record<string, any> | null;
  priority_score: number | null;
  priority_factors: any[] | null;
  data_quality: number | null;
}

export interface Candidate {
  equipment_id: string;
  tag: string;
  name: string;
  equipment_type: string;
  rank: number;
  score_pct: number;
  distance_m: number;
  bearing_alignment_deg: number;
  factors: { name: string; value: number; weight: number | string; contribution: number | null; detail: string }[];
}

export interface Evidence {
  kind: string;
  summary: string;
  detail: Record<string, any> | null;
  weight: number;
}

export interface Timeseries {
  ch4_by_sensor: Record<string, { t: string; ch4_ppm: number }[]>;
  process: { t: string; pressure_barg: number | null; flow_kg_h: number | null }[];
  wind: { t: string; wind_speed_ms: number; wind_dir_deg: number }[];
  markers: { t: string; label: string }[];
}

export interface AIInvestigation {
  id: number;
  provider: string;
  model: string;
  autonomy_level: number;
  tool_calls: { tool: string; arguments: Record<string, any> }[];
  report: {
    probable_source: string;
    confidence_pct: number;
    summary: string;
    alternative_candidates: { tag: string; score_pct: number; why_less_likely: string }[];
    key_evidence: string[];
    timeline: { time: string; what: string }[];
    uncertainties: string[];
    recommended_inspection: string;
    discipline: string;
    priority?: string;
    environmental_impact?: Record<string, any>;
    financial_impact?: Record<string, any>;
    emission_estimate?: Record<string, any>;
    authority_note?: string;
  };
  duration_ms: number;
  created_at?: string;
}

export interface WorkOrder {
  id: string;
  event_id: string | null;
  facility_id: string;
  equipment_id: string | null;
  title: string;
  description: string;
  discipline: string;
  priority: string;
  status: string;
  assignee: string | null;
  created_by: string;
  ai_drafted: boolean;
  created_at: string;
  updated_at: string;
  repair_completed_at: string | null;
  closed_at: string | null;
  audit_trail: { at: string; actor: string; action: string }[];
}

export interface Verification {
  outcome: string;
  verified_at: string;
  pre_mean_ppm: number;
  post_mean_ppm: number;
  pre_peak_ppm: number;
  post_peak_ppm: number;
  reduction_pct: number;
  ch4_avoided_kg_day: number;
  ch4_avoided_kg_year: number;
  gas_value_retained_omr_year: number;
  co2e_avoided_t_year: number;
  resolution_time_s: number;
  comparison_series: { pre: { t: string; ppm: number }[]; post: { t: string; ppm: number }[] } | null;
}

export interface AnalyticsSummary {
  window_days: number;
  methane_detected_kg: number;
  methane_avoided_kg_year_projection: number;
  financial_loss_detected_omr: number;
  gas_value_recovered_omr_year_projection: number;
  event_count: number;
  average_resolution_time_hours: number;
  recurring_equipment: { tag: string; name: string; event_count: number }[];
  events_by_severity: Record<string, number>;
  facility_comparison: { facility_id: string; facility_name: string; methane_kg: number; events: number; financial_omr: number }[];
  daily_methane_detected_kg: { date: string; methane_kg: number }[];
  verified_repair_count: number;
  note: string;
}

export interface DataSource {
  id: string;
  name: string;
  type: string;
  label: string;
  status: string;
  data_quality: number;
  latency_s: number | null;
  last_packet?: string | null;
  last_sync?: string | null;
  note: string;
  sensor_count?: number;
}

export interface DemoState {
  running: boolean;
  stage: string | null;
  event_id: string | null;
  started_at: string | null;
}
