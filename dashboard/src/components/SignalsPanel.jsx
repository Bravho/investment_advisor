import { Fragment, useState } from 'react'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const COMPS = ['value', 'quality', 'momentum', 'low_vol', 'dividend', 'technical', 'flows', 'fundamentals', 'sentiment']
const heat = (v) => v == null ? 'transparent' : `rgba(${v >= 50 ? '16,185,129' : '239,68,68'},${Math.abs(v - 50) / 50 * 0.7})`
const regimeTone = (r) => r === 'risk_on' ? 'green' : r === 'risk_off' ? 'red' : 'yellow'
const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')

export default function SignalsPanel({ payload, plans, loading, error, retry }) {
  const [open, setOpen] = useState(null)
  if (loading) return <Skeleton className="h-96" />
  if (error || !payload) return <Card><SectionTitle title="สัญญาณ" subtitle="Signals" /><ServiceError retry={retry} compact /></Card>
  const items = payload.items || []
  if (!items.length) return <Card><SectionTitle title="สัญญาณ" subtitle="Signals" /><p className="text-sm text-slate-500">No signal run yet.</p></Card>
  const reg = payload.regime || {}
  const ri = reg.inputs?.inputs || {}
  const pmap = Object.fromEntries((plans?.plans || []).map(p => [p.ticker, p]))
  return <Card>
    <SectionTitle title="สัญญาณการลงทุน" subtitle={`Signals · คะแนนจากองค์ประกอบที่ผ่าน walk-forward เท่านั้น (momentum / low-vol / technical) · หุ้นไทย = แสดงผลเท่านั้น (backtest อ่อน) · as of ${payload.as_of}`} action={<Badge tone={regimeTone(reg.regime)}>{String(reg.regime || '?').replace('_', '-')} ({number(reg.score, 2)})</Badge>} />
    <div className="mb-3 flex flex-wrap gap-2">{Object.entries(ri).map(([k, v]) => <span key={k} className="rounded-lg bg-[#141925] px-2 py-1 text-[10px] text-slate-400">{k} <b className="text-slate-200">{String(v)}</b></span>)}</div>
    <div className="overflow-auto"><table className="w-full text-[11px]">
      <thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">#</th><th className="text-left">Ticker</th><th className="text-right">Score</th><th className="text-right">Conf</th>{COMPS.map(c => <th key={c} className="px-0.5 text-center font-normal">{c.replace('_', ' ').slice(0, 7)}</th>)}<th className="text-left pl-2">Proposed plan (needs approval)</th></tr></thead>
      <tbody>{items.map(i => { const p = pmap[i.ticker]; return <Fragment key={i.ticker}>
        <tr className="cursor-pointer border-t border-slate-800/80 hover:bg-[#141925]" onClick={() => setOpen(open === i.ticker ? null : i.ticker)}>
          <td className="py-1 text-slate-500">{i.rank}</td>
          <td className="text-slate-200">{i.ticker}{i.kind === 'holding' && <span className="ml-1 text-[9px] text-sky-400">held</span>}{i.council?.verdict && <span className="ml-1 text-[9px] text-violet-300">★{i.council.verdict}</span>}</td>
          <td className="text-right font-semibold text-white">{number(i.score, 0)}</td>
          <td className="text-right text-slate-400">{number(i.confidence, 2)}</td>
          {COMPS.map(c => <td key={c} className="h-5 w-10 text-center text-[10px] text-white/80" style={{ background: heat(i.components?.[c]) }}>{i.components?.[c] == null ? '·' : Math.round(i.components[c])}</td>)}
          <td className="pl-2 text-slate-300 whitespace-nowrap">{p && p.entry_low ? <span className={p.viable ? '' : 'text-slate-500 line-through'}>{fmt(p.entry_low)}–{fmt(p.entry_high)} · SL {fmt(p.stop)} · TP {fmt(p.target)} · R:R {number(p.rr, 1)}{p.checklist_pass === false && <span className="ml-1 text-amber-300">⚠ checklist</span>}</span> : <span className="text-slate-600">{i.kind === 'holding' ? 'held' : 'no plan'}</span>}</td>
        </tr>
        {open === i.ticker && <tr><td colSpan={COMPS.length + 5} className="bg-[#0f131c] p-3 text-[11px] text-slate-300">
          {i.council && !i.council.error ? <div className="grid gap-3 md:grid-cols-2">
            <div><p className="font-semibold text-emerald-300">Bull case</p><ul className="list-disc pl-4">{(i.council.bull_case || []).map((b, k) => <li key={k}>{b}</li>)}</ul></div>
            <div><p className="font-semibold text-red-300">Bear case</p><ul className="list-disc pl-4">{(i.council.bear_case || []).map((b, k) => <li key={k}>{b}</li>)}</ul></div>
            <p className="md:col-span-2 text-slate-400">Key risk: {i.council.key_risk} · <i>{i.council.model}, facts-only prompt; LLM text can still err.</i></p>
          </div> : <p className="text-slate-500">Guru council runs for the top 5 ideas only.</p>}
          {p && <p className="mt-2 text-slate-400">{p.rationale}</p>}
          <p className="mt-1 text-[10px] text-slate-500">Price {i.inputs?.sources?.price?.source} ({i.inputs?.sources?.price?.as_of}) · fundamentals {i.inputs?.sources?.fundamentals?.source} ({i.inputs?.sources?.fundamentals?.as_of}) · benchmark {i.inputs?.sources?.benchmark}</p>
        </td></tr>}
      </Fragment>})}</tbody></table></div>
    <p className="mt-2 text-[10px] text-slate-500">{payload.method} Click a row for the council case and plan rationale.</p>
  </Card>
}
