export function CatalogSkeleton() {
  return (
    <div data-testid="catalog-skeleton" className="grid grid-cols-1 gap-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="h-24 rounded-xl bg-zinc-900 border border-zinc-800 animate-pulse"
          style={{ animationDelay: `${i * 80}ms` }}
        />
      ))}
    </div>
  )
}
