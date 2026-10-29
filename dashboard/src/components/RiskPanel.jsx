import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const thb = (v) => v == null ? '-' : `${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })} ฿`
const Stat = ({ label, value, sub }) => <div className="rounded-xl bg-[#141925] p-3"><p className="text-[10px] uppercase text-slate-500">{label}</p><p className="mt-1 text-sm font-semibold text-white">{value}</p>{sub && <p className="text-[10px] text-slate-500">{sub}</p>}</div>
const cellColor = (v) => v == null ? 'transparent' : v >= 0 ? `rgba(16,185,129,${Math.min(1, v) * 0.6})` : `rgba(239,68,68,${Math.min(1, -v) * 0.6})`

export default function RiskPanel({ report, loading, error, retry }) {
  if (loading) return <Skeleton className="h-96" />
  if (error || !report) return <Card><SectionTitle title="ความเสี่ยง" subtitle="Risk engine" />{error?.response?.status === 404 ? <p className="text-sm text-slate-500">No risk report yet.</p> : <ServiceError retry={retry} compact />}</Card>
  const s = report.summary || {}
  const v = report.var || {}
  const p = report.portfolio || {}
  const corr = report.correlation || { tickers: [], matrix: [] }
  const held = Object.keys(report.per_holding || {})
  const exp = report.factor_exposures?.portfolio?.betas || {}
  return <Card>
    <SectionTitle title="ความเสี่ยงพอร์ต" subtitle={`Risk engine · prices as of ${report.price_as_of} · run ${new Date(report.run_at).toLocaleString('en-GB', { timeZone: 'Asia/Bangkok' })} ICT`} action={report.provisional ? <Badge tone="yellow">provisional</Badge> : <Badge tone="green">confirmed</Badge>} />
    {report.provisional && <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-200">{report.provisional_note}</p>}
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      <Stat label="VaR 95% (1d, hist)" value={thb(v.hist_95?.var_thb)} sub={`ES ${thb(v.hist_95?.es_thb)} · ${number(v.hist_95?.var_pct, 2)}%`} />
      <Stat label="VaR 99% (1d, MC)" value={thb(v.mc_normal_99?.var_thb)} sub={`t(4) ${thb(v.mc_t4_99?.var_thb)} · hist ${thb(v.hist_99?.var_thb)}`} />
      <Stat label="Volatility (ann.)" value={`${number(p.vol_ann_pct, 1)}%`} sub={`beta to SET ${number(p.beta_set, 2)}`} />
      <Stat label="Max drawdown (3y)" value={`${number(p.max_drawdown_pct, 1)}%`} sub={`now ${number(p.current_drawdown_pct, 1)}%`} />
    </div>
    {(s.limit_breaches || []).length > 0 && <div className="mt-3 space-y-1">{s.limit_breaches.map(b => <p key={b} className="text-[11px] text-red-300">⚠️ {b}</p>)}</div>}
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <div><p className="mb-2 text-xs font-semibold text-slate-300">Stress scenarios</p>
        <table className="w-full text-xs"><tbody>{Object.entries(report.stress || {}).map(([k, sc]) => <tr key={k} className="border-t border-slate-800/80"><td className="py-1.5 pr-2 text-slate-300">{sc.label}</td><td className={`pr-2 text-right ${sc.pnl_thb < 0 ? 'text-red-400' : 'text-emerald-400'}`}>{thb(sc.pnl_thb)}</td><td className="text-right text-slate-400">{number(sc.pnl_pct, 1)}%</td></tr>)}</tbody></table>
        <p className="mt-2 text-xs font-semibold text-slate-300">Factor exposure (portfolio, 1y daily, R² {number(report.factor_exposures?.portfolio?.r2, 2)})</p>
        <div className="mt-1 flex flex-wrap gap-2">{Object.entries(exp).map(([f, b]) => <span key={f} className="rounded-lg bg-[#141925] px-2 py-1 text-[11px] text-slate-300">{f} <b className="text-white">{number(b, 3)}</b></span>)}</div>
        <p className="mt-1 text-[10px] text-slate-500">{report.factor_exposures?._units}</p>
        <p className="mt-2 text-xs font-semibold text-slate-300">Per holding</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Ticker</th><th className="text-right">Weight</th><th className="text-right">Vol</th><th className="text-right">β SET</th><th className="text-right">MDD</th></tr></thead><tbody>{held.map(t => { const h = report.per_holding[t]; return <tr key={t} className="border-t border-slate-800/80" title={h.data_note}><td className="py-1 text-slate-200">{t}</td><td className="text-right">{number(h.weight_pct, 1)}%</td><td className="text-right">{number(h.vol_ann_pct, 1)}%</td><td className="text-right">{number(h.beta_set, 2)}</td><td className="text-right">{number(h.max_drawdown_pct, 1)}%</td></tr> })}</tbody></table>
      </div>
      <div><p className="mb-2 text-xs font-semibold text-slate-300">Correlation (1y daily, holdings first)</p>
        <div className="overflow-auto"><table className="text-[9px]"><thead><tr><th></th>{corr.tickers.map(t => <th key={t} className="px-0.5 font-normal text-slate-500" style={{ writingMode: 'vertical-rl' }}>{t.replace('.BK', '')}</th>)}</tr></thead>
          <tbody>{corr.tickers.map((t, i) => <tr key={t}><td className="pr-1 text-slate-400 whitespace-nowrap">{t.replace('.BK', '')}</td>{corr.matrix[i].map((c, j) => <td key={j} title={`${t} / ${corr.tickers[j]}: ${c}`} className="h-4 w-4 text-center text-[8px] text-white/80" style={{ background: cellColor(c) }}>{i < 3 && c != null ? Math.round(c * 10) : ''}</td>)}</tr>)}</tbody></table></div>
        <p className="mt-2 text-[10px] text-slate-500">Data: {Object.entries(report.data_notes || {}).map(([k, n]) => `${k}: ${n}`).join(' · ')}</p>
      </div>
    </div>
  </Card>
}
