import { useState } from 'react'
import { portfolioClient } from '../config/api'
import { Badge, Card, SectionTitle, ServiceError, Skeleton, SourceBadge } from './UI'
import { number } from '../utils/format'

const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')

// Trade plans with approve / reject -> PATCH /trade-plans/{id} through the same-origin proxy (behind the auth proxy when remote).
export default function DeskPlans({ plans, journal, loading, error, retry }) {
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)
  if (loading) return <Skeleton className="h-64" />
  if (error || !plans) return <Card><SectionTitle title="Trade plans" /><ServiceError retry={retry} compact /></Card>
  const rows = [...(plans.plans || [])].sort((a, b) => (b.checklist_pass - a.checklist_pass) || (b.viable - a.viable) || ((b.rr || 0) - (a.rr || 0)))
  const act = async (p, status) => {
    const note = status === 'rejected' ? window.prompt(`Reject plan #${p.id} ${p.ticker}? Reason (optional):`, '') : (window.confirm(`Approve plan #${p.id} ${p.ticker}? This copies entry ${fmt(p.entry_low)}–${fmt(p.entry_high)}, stop ${fmt(p.stop)}, target ${fmt(p.target)} to the watch list (alerts only, no order is placed).`) ? '' : null)
    if (note === null) return
    setBusy(p.id); setMsg(null)
    try {
      const stamp = new Date().toLocaleString('en-GB', { timeZone: 'Asia/Bangkok' })
      await portfolioClient.patch(`/trade-plans/${p.id}`, { status, review_note: `${status} on trading desk ${stamp} ICT${note ? ': ' + note : ''}` })
      setMsg(`#${p.id} ${p.ticker} → ${status}`); retry()
    } catch (e) { setMsg(`#${p.id} failed: ${e?.response?.status || ''} ${e?.response?.data?.detail || e.message}`) }
    setBusy(null)
  }
  const newest = rows.reduce((m, p) => (p.updated_at > m ? p.updated_at : m), '')
  const j = journal?.items || []
  return <Card>
    <SectionTitle title="Trade plans" subtitle="Engine PROPOSED · approve/reject = PATCH /trade-plans/{id}" action={<div className="flex gap-1"><Badge tone="yellow">{rows.length} proposed</Badge><SourceBadge source="engine · yfinance" asOf={newest} /></div>} />
    {msg && <p className="mb-1 text-[11px] text-sky-300">{msg}</p>}
    <div className="max-h-[420px] overflow-auto"><table className="w-full text-[11px]">
      <thead className="sticky top-0 bg-[#151a24] text-[10px] uppercase text-slate-500"><tr><th className="text-left">#</th><th className="text-left">Ticker</th><th className="text-right">Last</th><th className="text-right">Entry</th><th className="text-right">Stop</th><th className="text-right">Target</th><th className="text-right">R:R</th><th className="text-right">Size</th><th>Chk</th><th>Price as of</th><th></th></tr></thead>
      <tbody>{rows.map(p => { const pa = p.inputs?.last_price?.as_of || p.inputs?.atr14?.as_of; return <tr key={p.id} className={`border-t border-slate-800/80 ${p.viable ? '' : 'text-slate-500'}`} title={p.rationale}>
        <td className="py-0.5 text-slate-500">{p.id}</td><td className="text-slate-200">{p.ticker}</td><td className="text-right">{fmt(p.last_price)}</td><td className="text-right">{fmt(p.entry_low)}–{fmt(p.entry_high)}</td>
        <td className="text-right text-red-300">{fmt(p.stop)}</td><td className="text-right text-emerald-300">{fmt(p.target)}</td><td className="text-right">{number(p.rr, 1)}</td>
        <td className="text-right">{p.size?.shares ?? '-'}</td><td className="text-center">{p.checklist_pass ? <Badge tone="green">pass</Badge> : <Badge tone="red">fail</Badge>}</td>
        <td className="text-center"><SourceBadge asOf={pa} staleHours={96} /></td>
        <td className="whitespace-nowrap text-right"><button disabled={busy === p.id} onClick={() => act(p, 'approved')} className="mr-1 rounded bg-emerald-700/70 px-2 py-0.5 text-[10px] text-white hover:bg-emerald-600 disabled:opacity-40">Approve</button>
          <button disabled={busy === p.id} onClick={() => act(p, 'rejected')} className="rounded bg-red-800/70 px-2 py-0.5 text-[10px] text-white hover:bg-red-700 disabled:opacity-40">Reject</button></td>
      </tr> })}</tbody></table></div>
    <div className="mt-3"><p className="mb-1 text-xs font-semibold text-slate-300">Journal <SourceBadge source="trade_journal" asOf={j[0]?.updated_at || j[0]?.created_at} staleHours={24 * 30} /></p>
      {j.length === 0 ? <p className="text-[11px] text-slate-500">No journal entries yet (POST /journal; PATCH /journal/&#123;id&#125; on exit).</p> :
        <table className="w-full text-[11px]"><tbody>{j.map(e => <tr key={e.id} className="border-t border-slate-800/80"><td>{e.ticker}</td><td>{e.opened_at}</td><td>{e.closed_at || 'open'}</td><td className="text-right">{number(e.pnl, 0)}</td><td className="text-right">{number(e.r_multiple, 2)}R</td><td>{e.grade || '-'}</td><td className="text-slate-400">{e.lessons || ''}</td></tr>)}</tbody></table>}
    </div>
  </Card>
}
