/** Mirrors emissiq.sim.scenario_fahud.DEMO_STAGES on the backend so the progress
 * rail the judge watches is the same list of steps the orchestrator executes. */
export const DEMO_STAGES = [
  { key: "normal", label: "Normal operation" },
  { key: "pressure_anomaly", label: "Pressure anomaly" },
  { key: "s3_detect", label: "Methane detected at S3" },
  { key: "s4_detect", label: "Methane detected at S4" },
  { key: "event_confirmed", label: "Event confirmed" },
  { key: "candidates", label: "Source candidates generated" },
  { key: "attributed", label: "Source attributed" },
  { key: "quantified", label: "Quantification completed" },
  { key: "prioritised", label: "Priority calculated" },
  { key: "investigated", label: "AI investigation completed" },
  { key: "recommended", label: "Action recommended" },
  { key: "work_order", label: "Work order created" },
  { key: "repaired", label: "Repair completed" },
  { key: "verifying", label: "Verification in progress" },
  { key: "avoided", label: "Emission avoided" },
] as const;
