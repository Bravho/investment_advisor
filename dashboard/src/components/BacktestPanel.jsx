import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const pct = (v, d = 1) => v == null ? '-' : `${(Number(v) * 100).toFixed(d)}%`

export default function BacktestPanel({ backtest, perf, paper, loading, error, retry }) {
  if (loading) return <Skeleton className="h-80" />
  if (error || !backtest) return <Card><SectionTitle title="ทดสอบย้อนหลัง" subtitle="Backtest & outcome scoring" /><ServiceError retry={retry} compact /></Card>
  const unis = backtest.universes || {}
  const live = (perf?.items || []).filter(i => i.source === 'live')
  const counts = paper?.counts || {}
  return <Card>
    <SectionTitle title="ทดสอบย้อนหลัง & ผลลัพธ์สัญญาณ" subtitle="Walk-forward backtest (out-of-sample only) · live signal outcomes · paper ledger" action={(perf?.weak || []).length ? <Badge tone="red">{perf.weak.length} weak</Badge> : <Badge tone="green">no weak flags</Badge>} />
    <div className="grid gap-4 xl:grid-cols-2">{Object.entries(unis).map(([u, r]) => <div key={u}>
      <p className="mb-1 text-xs font-semibold text-slate-300">{u === 'thai' ? 'Thai universe' : 'Global universe'} vs {r.benchmark?.ticker} · OOS {r.strategies?.combined?.oos_from} → {r.data_to}</p>
      <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Signal</th><th className="text-right">CAGR</th><th className="text-right">Sharpe</th><th className="text-right">MDD</th><th className="text-right">vs bench</th><th className="text-right">Hit</th><th className="text-right">Avg W/L</th><th></th></tr></thead>
        <tbody>{Object.entries(r.strategies || {}).map(([n, m]) => <tr key={n} className="border-t border-slate-800/80" title={(m.weak_reasons || []).join('; ')}>
          <td className="py-1 text-slate-200">{n}</td><td className="text-right">{pct(m.cagr)}</td><td className="text-right">{number(m.sharpe, 2)}</td><td className="text-right text-red-300">{pct(m.max_drawdown, 0)}</td>
          <td className={`text-right ${m.excess_cagr >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{pct(m.excess_cagr)}</td><td className="text-right">{pct(m.hit_rate, 0)}</td>
          <td className="text-right text-slate-400">{pct(m.avg_win)} / {pct(m.avg_loss)}</td><td className="pl-1">{m.weak ? <Badge tone="red">weak</Badge> : <Badge tone="green">ok</Badge>}</td></tr>)}
          <tr className="border-t border-slate-700 text-slate-400"><td className="py-1">buy & hold {r.benchmark?.ticker}</td><td className="text-right">{pct(r.benchmark?.cagr)}</td><td className="text-right">{number(r.benchmark?.sharpe, 2)}</td><td className="text-right">{pct(r.benchmark?.max_drawdown, 0)}</td><td colSpan={4}></td></tr>
        </tbody></table>
    </div>)}</div>
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <div><p className="mb-1 text-xs font-semibold text-slate-300">Live signal outcomes (20-session forward, score ≥ 60)</p>
        <table className="w-full text-[11px]"><thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Signal</th><th className="text-right">n</th><th className="text-right">Hit</th><th className="text-right">Avg W/L</th><th className="text-right">Sharpe</th><th></th></tr></thead>
          <tbody>{live.map(i => <tr key={i.signal} className="border-t border-slate-800/80"><td className="py-1 text-slate-200">{i.signal}</td><td className="text-right">{i.n}</td><td className="text-right">{pct(i.hit_rate, 0)}</td><td className="text-right">{pct(i.avg_win)} / {pct(i.avg_loss)}</td><td className="text-right">{number(i.sharpe, 2)}</td><td className="pl-1">{!i.sufficient ? <Badge tone="gray">n&lt;30</Badge> : i.weak ? <Badge tone="red">weak</Badge> : <Badge tone="green">ok</Badge>}</td></tr>)}</tbody></table>
        {!live.some(i => i.sufficient) && <p className="mt-1 text-[10px] text-slate-500">Signals started 2026-10-30; first outcomes mature after 20 sessions, and flags need n ≥ 30.</p>}
      </div>
      <div><p className="mb-1 text-xs font-semibold text-slate-300">Paper ledger (proposed plans, simulated)</p>
        <div className="flex gap-2 text-[11px]">{['waiting', 'open', 'closed', 'expired'].map(k => <span key={k} className="rounded-lg bg-[#141925] px-2 py-1 text-slate-300">{k} <b className="text-white">{counts[k] || 0}</b></span>)}</div>
        <p className="mt-1 text-[11px] text-slate-400">Hit rate {pct(paper?.hit_rate, 0)} · avg {paper?.avg_r == null ? '-' : `${number(paper.avg_r, 2)}R`}</p>
        <table className="mt-1 w-full text-[11px]"><tbody>{(paper?.trades || []).filter(t => t.status !== 'waiting').slice(0, 10).map(t => <tr key={t.id} className="border-t border-slate-800/80"><td className="py-1">{t.ticker}</td><td>{t.status}</td><td className="text-right">{t.entry_date} @ {number(t.entry_price, 2)}</td><td className="text-right">{t.exit_reason || ''}</td><td className="text-right">{t.r_multiple == null ? '' : `${number(t.r_multiple, 2)}R`}</td></tr>)}</tbody></table>
        <p className="mt-1 text-[10px] text-slate-500">{paper?.note}</p>
      </div>
    </div>
    <p className="mt-2 text-[10px] text-slate-500">Costs: Thai {pct(Object.values(unis)[0]?.config?.costs?.thai_side, 3)}/side (0.157% + VAT + 0.10% slippage); offshore {pct(Object.values(unis)[0]?.config?.costs?.offshore_side, 2)}/side; ETF TER accrued. Universe = today's watch list (survivorship bias - results flatter momentum).</p>
  </Card>
}
