export function FactorBar({
  name,
  value,
  detail,
  color = "var(--green)",
}: {
  name: string;
  value: number; // 0..1
  detail?: string;
  color?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="flex items-center justify-between mb-1">
        <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-dark)" }}>{name}</span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{pct.toFixed(0)}%</span>
      </div>
      <div className="factor-bar-track">
        <div className="factor-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      {detail && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>{detail}</div>}
    </div>
  );
}
