import { Fragment, useState } from 'react'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')
const mark = (p) => p === true ? '✅' : p === false ? '❌' : '–'

export default function TradePlansPanel({ plans, journal, loading, error, retry }) {
  const [open, setOpen] = useState(null)
  if (loading) return <Skeleton className="h-80" />
  if (error || !plans) return <Card><SectionTitle title="แผนการเทรด" subtitle="Trade plans" /><ServiceError retry={retry} compact /></Card>
  const rows = [...(plans.plans || [])].sort((a, b) => (b.viable - a.viable) || ((b.rr || 0) - (a.rr || 0)))
  const j = journal?.items || []
  return <Card>
    <SectionTitle title="แผนการเทรด & บันทึก" subtitle="Trade plans (engine-PROPOSED, need Tho's approval) · pre-trade checklist · journal" action={<Badge tone="yellow">{rows.length} proposed</Badge>} />
    <p className="mb-2 text-[11px] text-amber-200/80">Proposed plans never trigger alerts. Approving (PATCH /trade-plans/&#123;id&#125; status=approved) copies the zone/stop/target to the watch list, which then drives 'ready' alerts.</p>
    <div className="overflow-auto"><table className="w-full text-[11px]">
      <thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">#</th><th className="text-left">Ticker</th><th className="text-right">Last</th><th className="text-right">Entry</th><th className="text-right">Stop</th><th className="text-right">Target</th><th className="text-right">R:R</th><th className="text-right">Size</th><th className="text-center">Checklist</th><th className="text-left pl-2">Catalyst / expiry</th></tr></thead>
      <tbody>{rows.map(p => <Fragment key={p.id}>
        <tr className={`cursor-pointer border-t border-slate-800/80 hover:bg-[#141925] ${p.viable ? '' : 'text-slate-500'}`} onClick={() => setOpen(open === p.id ? null : p.id)}>
          <td className="py-1 text-slate-500">{p.id}</td><td className="text-slate-200">{p.ticker}</td><td className="text-right">{fmt(p.last_price)}</td>
          <td className="text-right">{fmt(p.entry_low)}–{fmt(p.entry_high)}</td><td className="text-right text-red-300">{fmt(p.stop)}</td><td className="text-right text-emerald-300">{fmt(p.target)}</td>
          <td className="text-right">{number(p.rr, 2)}{!p.viable && ' ✗'}</td>
          <td className="text-right">{p.size?.shares ?? '-'}<span className="text-slate-500"> sh{p.size?.position_pct != null ? ` · ${number(p.size.position_pct, 1)}%` : ''}</span></td>
          <td className="text-center">{p.checklist_pass ? <Badge tone="green">pass</Badge> : <Badge tone="red">fail</Badge>}</td>
          <td className="pl-2 text-slate-400">{(p.catalyst || '').replace(/ \(Yahoo.*\)/, '') || '-'} · exp {p.expiry}</td>
        </tr>
        {open === p.id && <tr><td colSpan={10} className="bg-[#0f131c] p-3 text-[11px] text-slate-300">
          <p className="mb-2 text-slate-400">{p.rationale}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <div><p className="font-semibold text-slate-200">Pre-trade checklist</p>{(p.checklist || []).map(c => <p key={c.check}>{mark(c.pass)} <b>{c.check}</b>{c.required ? '' : ' (advisory)'}: <span className="text-slate-400">{c.detail}</span></p>)}</div>
            <div><p className="font-semibold text-slate-200">Inputs (source · date)</p>{Object.entries(p.inputs || {}).map(([k, v]) => <p key={k}><b>{k}</b>: <span className="text-slate-400">{typeof v?.value === 'object' && v?.value ? (v.value.verdict || JSON.stringify(v.value)) : String(v?.value ?? v?.label ?? '')}{v?.label && v?.value != null && typeof v.value !== 'object' ? ` (${v.label})` : ''} · {v?.source || ''} {v?.as_of || ''}</span></p>)}</div>
          </div>
          <p className="mt-2 text-[10px] text-slate-500">Size from the risk engine's position sizer (same as /risk/position-size): {p.size?.binding_constraint} binding; risk budget {number(p.size?.risk_budget_thb, 0)} ฿; loss at stop {number(p.size?.loss_at_stop, 0)} (instrument ccy × FX {p.size?.fx_used}).</p>
        </td></tr>}
      </Fragment>)}</tbody></table></div>
    <div className="mt-4"><p className="mb-1 text-xs font-semibold text-slate-300">Trade journal</p>
      {j.length === 0 ? <p className="text-[11px] text-slate-500">No journal entries yet. POST /journal with plan_id, ticker, opened_at, entry_price, qty, fees, thesis; on exit PATCH closed_at, exit_price, followed_plan, exit_reason, what_went_well, what_went_wrong, lessons, emotion, grade (P&L and R-multiple are derived).</p> :
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Ticker</th><th>Opened</th><th>Closed</th><th className="text-right">P&L</th><th className="text-right">R</th><th>Followed plan</th><th>Grade</th><th className="text-left">Lesson</th></tr></thead>
          <tbody>{j.map(e => <tr key={e.id} className="border-t border-slate-800/80"><td className="py-1">{e.ticker}</td><td className="text-center">{e.opened_at}</td><td className="text-center">{e.closed_at || 'open'}</td><td className="text-right">{number(e.pnl, 0)}</td><td className="text-right">{number(e.r_multiple, 2)}</td><td className="text-center">{e.followed_plan == null ? '-' : e.followed_plan ? 'yes' : 'no'}</td><td className="text-center">{e.grade || '-'}</td><td className="text-slate-400">{e.lessons || ''}</td></tr>)}</tbody></table>}
    </div>
  </Card>
}
