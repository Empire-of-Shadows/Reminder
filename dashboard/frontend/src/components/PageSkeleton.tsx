export default function PageSkeleton() {
  return (
    <div className="page-skeleton" role="status" aria-live="polite" aria-busy="true">
      <div className="skeleton-bar skeleton-bar--lg" />
      <div className="skeleton-grid">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
      <span className="visually-hidden">Loading…</span>
    </div>
  );
}
