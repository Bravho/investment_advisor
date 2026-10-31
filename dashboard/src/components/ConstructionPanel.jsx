import { Badge, Card, SectionTitle, ServiceError, Skeleton, SourceBadge } from './UI'
import { number } from '../utils/format'

const LABEL = { thai_equity: 'Thai equities', gold: 'Gold', global_equity: 'Global equities', cash_bonds: 'Cash / bonds' }
const CLS = ['thai_equity', 'gold', 'global_equity', 'cash_bonds']

export default function ConstructionPanel({ data, loading, error, retry }) {
  if (loading) return <Skeleton className="h-72" />
  if (error || !data) return <Card><SectionTitle title="การจัดพอร์ต" subtitle="Portfolio construction" /><ServiceError retry={retry} compact /></Card>
  const w = data.weights || {}
  return <Card>
    <SectionTitle title="การจัดพอร์ต (DRAFT)" subtitle="Strategic + tactical tilt · risk parity · Black-Litterman · bands — suggestions only"
      action={<div className="flex gap-1"><Badge tone="yellow">DRAFT policy</Badge><SourceBadge source="engine · yfinance" asOf={data.created_at || data.as_of} /></div>} />
    <p className="mb-2 text-[11px] text-amber-200/80">{data.status}. Regime: {data.regime?.value || 'n/a'} ({data.regime?.as_of}). Value {number(data.portfolio_value_thb, 0)} ฿.</p>
    <div className="overflow-auto"><table className="w-full text-[11px]">
      <thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Class</th><th className="text-right">Current</th><th className="text-right">Range</th><th className="text-right">Strategic+tilt</th><th className="text-right">Risk parity</th><th className="text-right">Black-Litterman</th><th className="text-right">Recommended</th><th className="text-right">Drift</th><th className="text-center">Rebalance?</th></tr></thead>
      <tbody>{CLS.map(k => { const b = (data.bands || []).find(x => x.class === k) || {}; return <tr key={k} className="border-t border-slate-800/80">
        <td className="py-1 text-slate-200">{LABEL[k]}</td><td className="text-right">{number(data.current_pct?.[k], 1)}%</td><td className="text-right text-slate-500">{b.range?.join('–')}%</td>
        <td className="text-right">{number(w.strategic_plus_tilt?.[k], 1)}</td><td className="text-right">{number(w.risk_parity?.[k], 1)}</td><td className="text-right">{number(w.black_litterman?.[k], 1)}</td>
        <td className="text-right font-semibold text-emerald-300">{number(w.recommended?.[k], 1)}%</td><td className={`text-right ${Math.abs(b.drift_pp) > b.band_pp ? 'text-red-300' : ''}`}>{number(b.drift_pp, 1)} (±{number(b.band_pp, 1)})</td>
        <td className="text-center">{b.rebalance ? <Badge tone="red">yes</Badge> : <Badge tone="green">no</Badge>}</td></tr> })}</tbody></table></div>
    <p className="mb-1 mt-3 text-xs font-semibold text-slate-300">Suggested rebalance trades (not executed)</p>
    <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Ticker</th><th>Side</th><th className="text-right">Units</th><th className="text-right">Price</th><th className="text-right">Notional ฿</th><th className="text-right">Cost ฿</th><th className="text-right">Weight</th><th className="text-left pl-2">Tax / lot</th></tr></thead>
      <tbody>{(data.trades || []).map(t => <tr key={t.ticker} className="border-t border-slate-800/80"><td className="py-1">{t.ticker}</td><td className={`text-center ${t.side === 'BUY' ? 'text-emerald-300' : 'text-red-300'}`}>{t.side}</td><td className="text-right">{number(t.units, t.units % 1 ? 2 : 0)}</td><td className="text-right">{number(t.price_local, 2)}</td><td className="text-right">{number(t.notional_thb, 0)}</td><td className="text-right">{number(t.est_cost_thb, 0)}</td><td className="text-right">{number(t.from_pct, 1)}→{number(t.to_pct, 1)}%</td>
        <td className="pl-2 text-slate-400">{t.tax_lot ? `${t.tax_lot.method}; gain ≈ ${number(t.tax_lot.est_realised_gain_local, 0)}; ${t.tax_lot.tax}${t.tax_lot.xd_warning ? ' · ⚠ ' + t.tax_lot.xd_warning : ''}` : '-'}</td></tr>)}</tbody></table>
    <p className="mt-1 text-[11px] text-slate-400">Cash after trades ≈ {number(data.cash_after_trades_thb, 0)} ฿. BL views (1y, THB): {Object.entries(data.black_litterman?.views || {}).map(([k, v]) => `${LABEL[k]} ${number(v.view_1y_thb * 100, 1)}% (conf ${number(v.confidence, 2)})`).join(' · ')}</p>
    {(data.informational_not_actions || []).length > 0 && <div className="mt-2 rounded-lg border border-slate-700 bg-slate-800/40 p-2 text-[11px] text-slate-300"><b>ℹ️ Informational only (owner holds - no sell suggested):</b>{data.informational_not_actions.map(i => <p key={i.ticker}>{i.ticker}: {number(i.from_pct, 1)}% now vs model {number(i.model_target_pct, 1)}% - kept by Tho's decision.</p>)}{data.funding_note && <p className="mt-1 text-amber-200">{data.funding_note}</p>}</div>}
    <ul className="mt-1 list-disc pl-4 text-[10px] text-slate-500">{(data.notes || []).map(n => <li key={n}>{n}</li>)}</ul>
  </Card>
}
