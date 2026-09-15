export function StatCard({
  label,
  value,
  caption,
  captionColor = "var(--normal-green)",
  iconBg = "var(--normal-bg)",
  icon,
}: {
  label: string;
  value: string;
  caption?: string;
  captionColor?: string;
  iconBg?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="stat-card flex-1">
      <div className="flex items-center justify-between">
        <span className="stat-label">{label}</span>
        {icon && (
          <span className="stat-icon" style={{ background: iconBg }}>
            {icon}
          </span>
        )}
      </div>
      <div>
        <div className="stat-value">{value}</div>
        {caption && (
          <div className="stat-caption" style={{ color: captionColor }}>
            {caption}
          </div>
        )}
      </div>
    </div>
  );
}
