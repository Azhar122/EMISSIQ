export function fmtNum(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtOmr(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return `${fmtNum(v, digits)} OMR`;
}

export function fmtKgH(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${fmtNum(v, 1)} kg/h`;
}

export function fmtKg(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${fmtNum(v, 3)} kg`;
}

export function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "—";
  const pct = v <= 1 ? v * 100 : v;
  return `${fmtNum(pct, digits)}%`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function fmtTime(iso: string | null | undefined, locale = "en-US"): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function fmtDateTime(iso: string | null | undefined, locale = "en-US"): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(locale, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

export function severityBadgeClass(severity: string | null | undefined): string {
  switch ((severity || "").toLowerCase()) {
    case "critical": return "badge-critical";
    case "high": return "badge-high";
    case "medium": return "badge-medium";
    default: return "badge-normal";
  }
}

export function priorityBadgeClass(priority: string | null | undefined): string {
  switch ((priority || "").toLowerCase()) {
    case "critical": return "badge-critical";
    case "high": return "badge-high";
    case "medium": return "badge-medium";
    default: return "badge-low";
  }
}

export function statusBadgeClass(status: string | null | undefined): string {
  switch ((status || "").toLowerCase()) {
    case "closed": return "badge-normal";
    case "open": case "new": return "badge-info";
    case "investigating": case "in progress": return "badge-medium";
    case "verification": return "badge-high";
    default: return "badge-grey";
  }
}
