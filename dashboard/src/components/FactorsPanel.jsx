import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const TrendIcon = ({ trend }) => trend === 'up' ? <ArrowUpRight size={14} className="text-emerald-400" /> : trend === 'down' ? <ArrowDownRight size={14} className="text-red-400" /> : <ArrowRight size={14} className="text-slate-500" />
const when = (iso) => iso ? new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok' }) + ' ICT' : '-'
const chg = (v, unit) => v == null ? '-' : `${v > 0 ? '+' : ''}${number(v, 2)}${unit === '%' ? '%' : ''}`

export default function FactorsPanel({ payload, loading, error, retry }) {
  if (loading) return <Skeleton className="h-96" />
  const factors = payload?.factors || []
  return <Card>
    <SectionTitle title="ปัจจัยตลาด" subtitle={`Market factors · ${payload?.breached?.length || 0} past threshold${payload?.fred_key_valid ? '' : ' · FRED key invalid → free fallbacks'}`} />
    {error ? <ServiceError retry={retry} compact /> :
    <div className="grid gap-2 md:grid-cols-2">{factors.map(f => <div key={f.key} className={`rounded-xl border p-3 ${f.breached && !f.stale ? 'border-amber-500/40 bg-amber-500/5' : 'border-transparent bg-[#141925]'}`}>
      <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-white">{f.name}</span><div className="flex items-center gap-1">{f.breached && !f.stale && <Badge tone="yellow">alert</Badge>}{(f.stale || f.error) && <Badge tone="gray">{f.error ? 'error' : 'stale'}</Badge>}<TrendIcon trend={f.trend} /></div></div>
      <div className="mt-1 text-sm text-slate-200">{f.error ? <span className="text-red-300 text-xs">{f.error}</span> : (f.reading_text || `${number(f.reading, 2)} ${f.unit || ''}`)}</div>
      <div className="mt-1 flex gap-3 text-[10px] text-slate-400"><span>1d {chg(f.change_1d, f.change_unit)}</span><span>5d {chg(f.change_5d, f.change_unit)}</span><span>{f.change_unit}</span></div>
      {f.breach_reason && f.breached && <div className="mt-1 text-[10px] text-amber-300">⚠️ {f.breach_reason}</div>}
      <div className="mt-1 text-[10px] text-slate-500">Threshold: {f.threshold_text}</div>
      <div className="text-[10px] text-slate-500">Affects: {(f.affected_holdings || []).join(', ') || '-'}</div>
      <div className="text-[10px] text-slate-600">{f.source} · {when(f.as_of)}</div>
    </div>)}</div>}
  </Card>
}
