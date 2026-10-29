import { SourceBadge } from './UI'

// Data-source/timestamp strip above any panel (stale flag when older than staleHours).
export default function Stamp({ items = [], children }) {
  return <div>
    <div className="mb-1 flex flex-wrap justify-end gap-1">{items.filter(Boolean).map((i, k) => <SourceBadge key={k} source={i.source} asOf={i.asOf} staleHours={i.staleHours ?? 26} />)}</div>
    {children}
  </div>
}
