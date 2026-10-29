import { Badge, Card, SectionTitle, ServiceError, Skeleton, SourceBadge } from './UI'
import { number } from '../utils/format'

const LABEL = { thai_equity: 'Thai eq', gold: 'Gold', global_equity: 'Global eq', cash_bonds: 'Cash' }
const S = ({ s }) => s?.n_days >= 5 ? <><td className="text-right">{number(s.total_return_pct, 2)}%</td><td className="text-right">{number(s.annualised_pct, 1)}%</td><td className="text-right">{number(s.vol_pct, 1)}%</td><td className="text-right">{number(s.sharpe, 2)}</td><td className="text-right">{number(s.sortino, 2)}</td><td className="text-right">{number(s.max_drawdown_pct, 1)}%</td><td className="text-right">{number(s.calmar, 2)}</td></> : <td colSpan={7} className="text-slate-500">n/a</td>

function Window({ w }) {
  if (!w) return null
  const a = w.attribution_vs_policy || {}
  const rows = [['Portfolio', w.portfolio], ['SET TRI proxy (TDEX)', w.benchmarks?.set_tri_proxy_TDEX], ['Gold (THB)', w.benchmarks?.gold_thb], ['Policy benchmark (DRAFT)', w.benchmarks?.policy_benchmark]]
  const al = w.alpha || {}
  const fa = (x, k) => x?.alpha_ann_pct == null ? 'n/a (too few days)' : `α ${number(x.alpha_ann_pct, 1)}%/yr (t ${number(x.alpha_t, 1)}), β ${number(x[`beta_${k}`], 2)}`
  return <div className="mb-4">
    <p className="text-xs font-semibold text-slate-300">{w.label} <span className="font-normal text-slate-500">{w.start} → {w.end} · {w.portfolio?.n_days} days</span> {w.portfolio?.significance !== 'ok' && <Badge tone="yellow">{w.portfolio?.significance}</Badge>}</p>
    <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Series</th><th className="text-right">Return</th><th className="text-right">Ann.</th><th className="text-right">Vol</th><th className="text-right">Sharpe</th><th className="text-right">Sortino</th><th className="text-right">MaxDD</th><th className="text-right">Calmar</th></tr></thead>
      <tbody>{rows.map(([n, s]) => <tr key={n} className="border-t border-slate-800/80"><td className="py-0.5">{n}</td><S s={s} /></tr>)}</tbody></table>
    {w.mwr && <p className="mt-1 text-[11px] text-slate-400">TWR {number(w.twr_pct, 2)}% · MWR (on cost {number(w.mwr.cost_basis_thb, 0)} ฿) {number(w.mwr.period_return_on_cost_pct, 2)}% over {w.mwr.days} days — {w.mwr.flows}</p>}
    <p className="mt-1 text-[11px] text-slate-400">Alpha vs SET TRI proxy: {fa(al.vs_set_tri_proxy, 'tdex')} · vs gold: {fa(al.vs_gold, 'gold')}</p>
    <p className="mt-1 text-[11px] text-slate-300">Attribution vs policy (active {number(a.active_log_pct, 2)}%): allocation {number(a.allocation_total_pct, 2)} · selection {number(a.selection_total_pct, 2)} · currency {number(a.currency_pct, 2)} · timing {number(a.timing_pct, 2)} · residual {number(a.residual_pct, 2)}
      <span className="text-slate-500"> | alloc by class: {Object.entries(a.allocation_pct || {}).map(([k, v]) => `${LABEL[k]} ${number(v, 2)}`).join(', ')}; avg weights: {Object.entries(a.avg_weights_pct || {}).map(([k, v]) => `${LABEL[k]} ${v}%`).join(', ')}</span></p>
  </div>
}

export default function AttributionPanel({ data, loading, error, retry }) {
  if (loading) return <Skeleton className="h-72" />
  if (error || !data) return <Card><SectionTitle title="ผลการดำเนินงาน" subtitle="Performance & attribution" /><ServiceError retry={retry} compact /></Card>
  return <Card>
    <SectionTitle title="ผลการดำเนินงาน & ที่มา" subtitle="TWR/MWR · Sharpe/Sortino/Calmar · alpha vs SET TRI proxy & gold · allocation/selection/currency/timing"
      action={<SourceBadge source="yfinance TR · holdings" asOf={data.created_at || data.as_of} />} />
    <Window w={data.live} /><Window w={data.proforma_1y} /><Window w={data.proforma_3y} />
    <ul className="list-disc pl-4 text-[10px] text-slate-500">{(data.notes || []).map(n => <li key={n}>{n}</li>)}<li>Recorded daily totals not used: {data.recorded_series_audit?.why_not_used}</li><li>Risk-free {number(data.risk_free_pct, 2)}% ({data.rf_source}).</li></ul>
  </Card>
}
