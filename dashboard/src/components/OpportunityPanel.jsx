import { X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { number, percent } from '../utils/format'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'

const signalTone = { strong_opportunity: 'emerald', opportunity: 'blue', neutral: 'gray', avoid: 'red' }

export default function OpportunityPanel({ opportunities = [], loading, error, retry }) {
  const [selected, setSelected] = useState(null)
  const sorted = useMemo(() => [...(opportunities || [])].sort((a, b) => Number(b.opportunity_score) - Number(a.opportunity_score)), [opportunities])
  if (loading) return <Skeleton className="h-96" />
  return <><Card className="h-full"><SectionTitle title="สแกนโอกาส" subtitle="Opportunity scanner" />
    {error ? <ServiceError retry={retry} compact /> : !sorted.length ? <p className="py-16 text-center text-sm text-slate-500">ยังไม่พบโอกาสใน watchlist</p> :
    <div className="space-y-2">{sorted.map(item => <button key={item.ticker} onClick={() => setSelected(item)} className="w-full rounded-xl border border-transparent bg-[#141925] p-3 text-left transition hover:border-emerald-500/30"><div className="flex items-center justify-between"><span className="rounded-lg bg-slate-700/60 px-2 py-1 text-xs font-bold text-white">{item.ticker}</span><Badge tone={signalTone[item.signal]}>{item.signal?.replace('_', ' ')}</Badge></div><div className="mt-3 flex items-center gap-3"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-400" style={{ width: `${Math.min(100, Number(item.opportunity_score) || 0)}%` }} /></div><span className="w-9 text-right text-xs font-semibold text-white">{number(item.opportunity_score, 0)}</span></div><div className="mt-2 flex justify-between text-[10px] text-slate-500"><span>RSI {number(item.rsi, 1)}</span><span>{item.suggested_action}</span></div></button>)}</div>}
  </Card>
  {selected && <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4" onClick={() => setSelected(null)}><Card className="w-full max-w-lg" onClick={event => event.stopPropagation()}><div className="flex items-start justify-between"><div><p className="text-2xl font-bold text-white">{selected.ticker}</p><Badge tone={signalTone[selected.signal]}>{selected.signal}</Badge></div><button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white"><X /></button></div><div className="mt-6 grid grid-cols-2 gap-3">{[['Opportunity score', number(selected.opportunity_score)], ['Confidence', percent(Number(selected.confidence) * 100)], ['RSI', number(selected.rsi)], ['Price vs SMA20', selected.price_vs_sma20], ['Sentiment', selected.sentiment_signal], ['Volume', selected.volume_signal]].map(([key, value]) => <div key={key} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] uppercase text-slate-500">{key}</p><p className="mt-1 text-sm font-medium text-white">{value || '-'}</p></div>)}</div><p className="mt-5 text-xs text-slate-500">Scanned: {selected.scanned_at ? new Date(selected.scanned_at).toLocaleString('th-TH') : '-'}</p></Card></div>}
  </>
}
