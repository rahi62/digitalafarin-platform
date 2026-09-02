type MetricCardProps = {
  label: string;
  value: string;
  hint: string;
  level?: number;
  state?: "normal" | "warning" | "danger";
};

export function MetricCard({ label, value, hint, level, state = "normal" }: MetricCardProps) {
  return (
    <article className={`metricCard metric-${state}`}>
      <div className="metricTopline"><span>{label}</span><span className="metricStateDot" /></div>
      <strong className="metricValue" dir="ltr">{value}</strong>
      {typeof level === "number" ? (
        <div className="meterTrack" aria-label={`${label}: ${level}%`}>
          <span className="meterFill" style={{ width: `${Math.min(100, Math.max(0, level))}%` }} />
        </div>
      ) : null}
      <small>{hint}</small>
    </article>
  );
}
