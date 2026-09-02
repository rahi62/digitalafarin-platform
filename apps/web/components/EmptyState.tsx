export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="emptyState">
      <div className="emptyIcon" aria-hidden="true">—</div>
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}
