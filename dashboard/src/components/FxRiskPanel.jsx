import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

// 2026-10-31: FX (currency) risk panel - Tho: "include the risk of foreign currency rate changing".
const thb = (v) => v == null ? '-' : `${v > 0 ? '+' : ''}${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })} ฿`
const pct = (v, d = 2) => v == null ? '-' : `${v > 0 ? '+' : ''}${number(v, d)}%`
const tone = (v) => v == null ? 'text-slate-400' : v < 0 ? 'text-red-400' : 'text-emerald-400'
const share = (v) => v == null ? <span className="text-amber-300">unknown</span> : `${Math.round(v * 100)}%`

export default function FxRiskPanel({ report, loading, error, retry }) {
  if (loading) return <Skeleton className="h-96" />
  if (error || !report || report.error) return <Card><SectionTitle title="ความเสี่ยงค่าเงิน (FX)" subtitle="FX risk" /><ServiceError retry={retry} compact /></Card>
  const s = report.summary || {}
  const pairs = report.pairs || {}
  const vs = report.variance_split?.share_of_variance_pct || {}
  return <Card>
    <SectionTitle title="ความเสี่ยงค่าเงิน (FX)" subtitle={`USD/THB ขึ้น = บาทอ่อน · generated ${new Date(report.generated_at).toLocaleString('en-GB', { timeZone: 'Asia/Bangkok' })} ICT`}
      action={<Badge tone={Math.abs(s.portfolio_fx_beta || 0) > 0.3 ? 'yellow' : 'gray'}>FX β {number(s.portfolio_fx_beta, 2)}</Badge>} />
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      {Object.entries(pairs).map(([k, p]) => <div key={k} className="rounded-xl bg-[#141925] p-2" title={`${p.unit} · 1y range ${p.low_1y}-${p.high_1y} · vol 1y ${p.vol_1y_ann_pct}%`}>
        <p className="text-[10px] uppercase text-slate-500">{p.label}</p>
        <p className="text-sm font-semibold text-white">{number(p.last, k === 'JPYTHB' ? 4 : 3)}</p>
        <p className="text-[10px] text-slate-400">1d <span className={tone(p.chg_1d_pct)}>{pct(p.chg_1d_pct)}</span> · 1m <span className={tone(p.chg_1m_pct)}>{pct(p.chg_1m_pct)}</span> · 1y {pct(p.chg_1y_pct, 1)}</p>
        <p className="text-[10px] text-slate-500">vol 3m {number(p.vol_3m_ann_pct, 1)}% · {number(p.pct_of_1y_range, 0)}% of 1y range · {p.as_of}</p>
      </div>)}
    </div>
    <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4 text-xs">
      <div className="rounded-xl bg-[#141925] p-2"><p className="text-[10px] uppercase text-slate-500">Net direct FX (unhedged)</p><p className="font-semibold text-white">{number(s.net_direct_fx_thb, 0)} ฿</p><p className="text-[10px] text-slate-500">{number(s.net_direct_fx_pct, 1)}% of book · unknown {number(s.unknown_direct_thb, 0)} ฿</p></div>
      <div className="rounded-xl bg-[#141925] p-2"><p className="text-[10px] uppercase text-slate-500">FX VaR95</p><p className="font-semibold text-white">{number(report.fx_var?.var95_1d_thb, 0)} ฿ / 1d</p><p className="text-[10px] text-slate-500">{number(report.fx_var?.var95_1m_thb, 0)} ฿ / 1m (FX leg only)</p></div>
      <div className="rounded-xl bg-[#141925] p-2"><p className="text-[10px] uppercase text-slate-500">Baht 10% stronger</p><p className={`font-semibold ${tone(s.thb_plus10_pnl_thb)}`}>{thb(s.thb_plus10_pnl_thb)}</p><p className="text-[10px] text-slate-500">baht 10% weaker {thb(s.thb_minus10_pnl_thb)}</p></div>
      <div className="rounded-xl bg-[#141925] p-2"><p className="text-[10px] uppercase text-slate-500">FX share of variance</p><p className="font-semibold text-white">{number(vs.usdthb, 1)}%</p><p className="text-[10px] text-slate-500">SET {number(vs.set, 0)}% · gold {number(vs.gold, 0)}% · Brent {number(vs.brent, 0)}%</p></div>
    </div>
    <p className="mb-1 mt-4 text-xs font-semibold text-slate-300">Exposure per holding</p>
    <div className="overflow-auto"><table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Ticker</th><th className="text-right">Weight</th><th className="text-right">Direct FX</th><th className="text-right">Hedged</th><th className="text-right">β assumed</th><th className="text-right">β measured total (t)</th><th className="text-right">β used</th><th className="text-right">฿ per 1%</th></tr></thead>
      <tbody>{(report.positions || []).map(l => <tr key={l.ticker} className="border-t border-slate-800/80" title={`${l.basis || ''}\n${l.hedge_note || ''}\nsource: ${l.source || l.registry}`}>
        <td className="py-1 text-slate-200">{l.ticker}</td><td className="text-right">{number(l.weight_pct, 1)}%</td><td className="text-right">{share(l.direct_foreign_share)}</td><td className="text-right">{share(l.hedge_ratio)}</td>
        <td className="text-right">{l.beta_assumed == null ? '-' : number(l.beta_assumed, 2)}</td><td className="text-right" title={l.beta_partial == null ? 'total beta (USD/THB only)' : `partial beta holding SET/Brent constant: ${number(l.beta_partial, 2)} (t ${number(l.beta_partial_t, 1)})`}>{l.beta_measured == null ? '-' : `${number(l.beta_measured, 2)} (${number(l.beta_measured_t, 1)})`}</td>
        <td className="text-right font-semibold text-white" title={l.beta_basis}>{number(l.beta_used, 2)}</td><td className="text-right">{thb(l.fx_value_at_risk_per_1pct_thb)}</td></tr>)}</tbody></table></div>
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <div><p className="mb-1 text-xs font-semibold text-slate-300">USD/THB scenarios (FX leg only)</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Scenario</th><th className="text-right">Economic</th><th className="text-right">Direct only</th></tr></thead>
          <tbody>{(report.scenarios || []).map(sc => <tr key={sc.usdthb_move_pct} className="border-t border-slate-800/80"><td className="py-1 text-slate-300">{sc.label}</td><td className={`text-right ${tone(sc.economic_pnl_thb)}`}>{thb(sc.economic_pnl_thb)} ({pct(sc.economic_pnl_pct)})</td><td className={`text-right ${tone(sc.direct_only_pnl_thb)}`}>{thb(sc.direct_only_pnl_thb)}</td></tr>)}
            {Object.entries(report.historical_1m_extremes || {}).filter(([k]) => k !== 'window').map(([k, h]) => <tr key={k} className="border-t border-slate-800/80"><td className="py-1 text-slate-400">{k.replaceAll('_', ' ')} ({h.end_date}, {pct(h.usdthb_move_pct)})</td><td className={`text-right ${tone(h.fx_leg_pnl_thb_on_today_book)}`}>{thb(h.fx_leg_pnl_thb_on_today_book)}</td><td></td></tr>)}</tbody></table>
      </div>
      <div><p className="mb-1 text-xs font-semibold text-slate-300">FX assumption per forecast horizon</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Horizon</th><th className="text-right">USD/THB median</th><th className="text-right">80% range</th><th className="text-right">FX-leg ฿ (median)</th></tr></thead>
          <tbody>{(report.forecast_fx_assumptions || []).map(f => <tr key={f.horizon} className="border-t border-slate-800/80"><td className="py-1 text-slate-300">{f.horizon}</td>{f.usdthb_median ? <><td className="text-right">{number(f.usdthb_median, 2)}</td><td className="text-right">{number(f.usdthb_80pct?.[0], 2)}–{number(f.usdthb_80pct?.[1], 2)}</td><td className={`text-right ${tone(f.fx_leg_pnl_at_median_thb)}`}>{thb(f.fx_leg_pnl_at_median_thb)}</td></> : <td colSpan={3} className="text-right text-slate-500">{f.status}</td>}</tr>)}</tbody></table>
        {Object.keys(report.scbgolde_gold_vs_fx || {}).length > 0 && <><p className="mb-1 mt-3 text-xs font-semibold text-slate-300">SCBGOLDE: gold vs FX (unhedged)</p>
          <table className="w-full text-[11px]"><tbody>{Object.entries(report.scbgolde_gold_vs_fx).map(([k, g]) => <tr key={k} className="border-t border-slate-800/80"><td className="py-1 text-slate-300">{k}</td><td className="text-right">gold USD {pct(g.asset_return_usd_pct)}</td><td className={`text-right ${tone(g.fx_return_pct)}`}>FX {pct(g.fx_return_pct)}</td><td className="text-right text-white">THB {pct(g.total_return_thb_pct)}</td></tr>)}</tbody></table></>}
      </div>
    </div>
    {(report.open_questions || []).length > 0 && <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-200"><b>Open questions (not guessed):</b><ul className="list-disc pl-4">{report.open_questions.map(q => <li key={q}>{q}</li>)}</ul></div>}
    <ul className="mt-2 list-disc pl-4 text-[10px] text-slate-500">{(report.caveats || []).map(c => <li key={c}>{c}</li>)}</ul>
    <p className="mt-1 text-[10px] text-slate-500">{report.fx_convention} Sources: {report.sources?.fx}; registry {report.sources?.registry}. Advisory only.</p>
  </Card>
}
