import { useState } from 'react'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const H = ['3d', '1m', '3m', '6m', '1y']
const pct = (v, d = 0) => v == null ? '-' : `${(Number(v) * 100).toFixed(d)}%`
const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')
const covTone = (c, nom) => c == null ? 'gray' : Math.abs(c - nom) <= 0.05 ? 'green' : Math.abs(c - nom) <= 0.12 ? 'yellow' : 'red'

export default function PredictionsPanel({ preds, board, loading, error, retry }) {
  const [kind, setKind] = useState('holding')
  if (loading) return <Skeleton className="h-96" />
  if (error || !preds || !board) return <Card><SectionTitle title="การพยากรณ์" subtitle="Forecasts" /><ServiceError retry={retry} compact /></Card>
  const items = preds.items || []
  const subjects = [...new Set(items.filter(p => p.subject_type === kind).map(p => p.subject))]
  const by = {}
  items.forEach(p => { (by[p.subject] = by[p.subject] || {})[p.horizon] = p })
  const rows = board.rows || []
  const weights = board.model_weights || []
  const models = [...new Set(weights.map(w => w.model))].filter(m => !m.startsWith('_'))
  return <Card>
    <SectionTitle title="การพยากรณ์ & สกอร์บอร์ด" subtitle="Frozen forecasts (3d · 1m · 3m · 6m · 1y) · validation · learning loop" action={<div className="flex gap-1">{['holding', 'idea', 'factor'].map(k => <button key={k} onClick={() => setKind(k)} className={`rounded px-2 py-0.5 text-[10px] ${kind === k ? 'bg-sky-600 text-white' : 'bg-[#141925] text-slate-400'}`}>{k}s</button>)}</div>} />
    <div className="overflow-auto"><table className="w-full text-[11px]">
      <thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Subject</th><th className="text-right">Base</th>{H.map(h => <th key={h} className="text-center">{h} · P(up) · 80% range</th>)}</tr></thead>
      <tbody>{subjects.map(s => { const r = by[s]; const any = Object.values(r)[0]; return <tr key={s} className="border-t border-slate-800/80">
        <td className="py-1 text-slate-200">{s}</td><td className="text-right text-slate-400">{fmt(any?.base_price)}</td>
        {H.map(h => { const p = r[h]; return <td key={h} className="px-1 text-center" title={p ? `made ${p.made_at} · target ${p.target_date} · conf ${p.confidence} · sha ${p.payload_sha256?.slice(0, 10)}` : ''}>{p ? <span><b className={p.direction === 'up' ? 'text-emerald-400' : 'text-red-400'}>{p.direction === 'up' ? '▲' : '▼'} {pct(p.p_up)}</b> <span className="text-slate-500">{fmt(p.band80_low)}–{fmt(p.band80_high)}</span></span> : '-'}</td> })}
      </tr> })}</tbody></table></div>
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <div><p className="mb-1 text-xs font-semibold text-slate-300">Scoreboard (validated outcomes)</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Horizon</th><th>Source</th><th className="text-right">n</th><th className="text-right">Dir. hit</th><th className="text-right">50% cov</th><th className="text-right">80% cov</th><th className="text-right">95% cov</th><th className="text-right">Brier</th></tr></thead>
          <tbody>{rows.map(r => <tr key={r.horizon + r.source} className="border-t border-slate-800/80"><td className="py-1">{r.horizon}</td><td className="text-center text-slate-400">{r.source}</td><td className="text-right">{r.n}</td>
            <td className={`text-right ${r.hit > 0.52 ? 'text-emerald-400' : r.hit < 0.5 ? 'text-red-400' : ''}`}>{pct(r.hit)}</td>
            <td className="text-right"><Badge tone={covTone(r.c50, 0.5)}>{pct(r.c50)}</Badge></td><td className="text-right"><Badge tone={covTone(r.c80, 0.8)}>{pct(r.c80)}</Badge></td><td className="text-right"><Badge tone={covTone(r.c95, 0.95)}>{pct(r.c95)}</Badge></td><td className="text-right">{number(r.brier, 3)}</td></tr>)}</tbody></table>
        <p className="mt-1 text-[10px] text-slate-500">Pending live (not yet matured): {Object.entries(board.pending_live || {}).map(([h, n]) => `${h} ${n}`).join(' · ') || 'none'}. Backfill = historical walk-forward, price-only models, data ≤ each as-of date. Brier 0.25 = coin flip.</p>
        <p className="mt-2 mb-1 text-xs font-semibold text-slate-300">Misses by root cause</p>
        <div className="flex flex-wrap gap-1">{Object.entries((board.rca_counts || []).reduce((a, r) => ({ ...a, [r.rca_primary]: (a[r.rca_primary] || 0) + r.n }), {})).sort((a, b) => b[1] - a[1]).map(([k, n]) => <span key={k} className="rounded-lg bg-[#141925] px-2 py-1 text-[10px] text-slate-300">{k} <b className="text-white">{n}</b></span>)}</div>
      </div>
      <div><p className="mb-1 text-xs font-semibold text-slate-300">Model weights per horizon (learning loop)</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Model</th>{H.map(h => <th key={h} className="text-right">{h}</th>)}</tr></thead>
          <tbody>{models.map(m => <tr key={m} className="border-t border-slate-800/80"><td className="py-1 text-slate-200">{m}</td>{H.map(h => { const w = weights.find(x => x.model === m && x.horizon === h); return <td key={h} className="text-right" title={w?.basis}>{!w ? '-' : w.status === 'retired' ? <span className="text-red-400">retired</span> : <span className={w.status === 'prior' ? 'text-slate-500' : ''}>{number(w.weight, 2)}</span>}</td> })}</tr>)}
            <tr className="border-t border-slate-700"><td className="py-1 text-slate-400">σ multiplier</td>{H.map(h => { const w = weights.find(x => x.model === '_sigma_scale' && x.horizon === h); return <td key={h} className="text-right text-slate-400" title={w?.basis}>{w ? `×${number(w.weight, 2)}` : '-'}</td> })}</tr></tbody></table>
        <p className="mt-2 mb-1 text-xs font-semibold text-slate-300">Lessons (fed to the advisor)</p>
        <ul className="list-disc pl-4 text-[11px] text-slate-400">{(board.lessons || []).slice(0, 8).map((l, i) => <li key={i}>{l.lesson}</li>)}</ul>
      </div>
    </div>
  </Card>
}
