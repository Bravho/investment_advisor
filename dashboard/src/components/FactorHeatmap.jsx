import { Card, SectionTitle, ServiceError, Skeleton, SourceBadge } from './UI'
import { number } from '../utils/format'

const cell = (b, t) => {
  const a = Math.min(Math.abs(b || 0) / 0.6, 1) * (Math.abs(t || 0) >= 2 ? 1 : 0.35)
  return { backgroundColor: b >= 0 ? `rgba(16,185,129,${a})` : `rgba(239,68,68,${a})` }
}

// Holdings x factor betas (1y daily regression, risk engine) + factor moves strip (market_factors)
export default function FactorHeatmap({ report, factors, loading, error, retry }) {
  if (loading) return <Skeleton className="h-48" />
  if (error || !report) return <Card><SectionTitle title="Factor heatmap" /><ServiceError retry={retry} compact /></Card>
  const fe = report.factor_exposures || {}
  const rows = Object.keys(fe).filter(k => !k.startsWith('_'))
  const cols = Object.keys(fe.portfolio?.betas || fe[rows[0]]?.betas || {})
  const fl = factors?.factors || []
  return <Card>
    <SectionTitle title="Factor heatmap" subtitle="Beta per 1% factor move (1y daily OLS); faded = |t| < 2" action={<SourceBadge source="risk engine · yfinance" asOf={report.run_at || report.generated_at} />} />
    <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Position</th>{cols.map(c => <th key={c} className="text-center">{c}</th>)}<th className="text-right">R²</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r} className={`border-t border-slate-800/80 ${r === 'portfolio' ? 'font-semibold' : ''}`}><td className="py-0.5">{r}</td>
        {cols.map(c => <td key={c} className="text-center" style={cell(fe[r].betas?.[c], fe[r].t_stats?.[c])} title={`t = ${fe[r].t_stats?.[c] ?? 'n/a'}`}>{number(fe[r].betas?.[c], 2)}</td>)}
        <td className="text-right text-slate-400">{number(fe[r].r2, 2)}</td></tr>)}</tbody></table>
    <div className="mt-3 flex flex-wrap gap-1">{fl.map(f => <span key={f.key} title={`${f.source} · ${f.breach_reason || ''}`}
      className={`rounded px-1.5 py-0.5 text-[10px] ${f.stale ? 'border border-red-500/60 text-red-300' : ''}`}
      style={{ backgroundColor: f.change_1d == null ? '#1e2330' : f.change_1d >= 0 ? `rgba(16,185,129,${Math.min(Math.abs(f.change_1d) / 3, 1) * 0.8})` : `rgba(239,68,68,${Math.min(Math.abs(f.change_1d) / 3, 1) * 0.8})` }}>
      {f.key} {f.change_1d == null ? '' : `${number(f.change_1d, 1)}${f.change_unit || ''}`}{f.breached ? ' ⚑' : ''}{f.stale ? ' STALE' : ''}</span>)}</div>
    <div className="mt-1"><SourceBadge source="market_factors" asOf={fl.reduce((m, f) => (f.updated_at && f.updated_at > m ? f.updated_at : m), '')} staleHours={3} /></div>
  </Card>
}
