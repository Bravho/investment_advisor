import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

const statusTone = { ready: 'green', watching: 'blue', dropped: 'gray' }
const ago = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'Asia/Bangkok' })
}
const zone = (lo, hi) => (lo == null && hi == null ? <span className="text-slate-600">not set</span> : `${lo ?? '-'} – ${hi ?? '-'}`)

export default function WatchlistPanel({ payload, loading, error, retry }) {
  if (loading) return <Skeleton className="h-96" />
  const items = payload?.items || []
  return <Card>
    <SectionTitle title="รายการเฝ้าดูการลงทุน" subtitle={`Investment watch list · ${items.length} ideas · prices stale after ${payload?.stale_after_days ?? 7} days`} />
    {error ? <ServiceError retry={retry} compact /> : !items.length ? <p className="py-10 text-center text-sm text-slate-500">No watch-list items</p> :
    <div className="max-h-[520px] overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-[#1a1f2e] text-[10px] uppercase text-slate-500">
          <tr><th className="py-2 pr-2">Ticker</th><th className="pr-2">Status</th><th className="pr-2 text-right">Price</th><th className="pr-2 text-right">1d</th><th className="pr-2 text-right">RSI</th><th className="pr-2">Entry zone</th><th className="pr-2">Target</th><th className="pr-2 text-right">Score</th><th>Alerts</th></tr>
        </thead>
        <tbody>{items.map(item => {
          const m = item.metrics || {}
          const chg = m.change_1d_pct
          return <tr key={item.ticker} className="border-t border-slate-800/80 align-top" title={item.thesis || ''}>
            <td className="py-2 pr-2"><div className="font-semibold text-white">{item.ticker}</div><div className="text-[10px] text-slate-500">{item.name} · {item.sector}</div></td>
            <td className="pr-2"><Badge tone={statusTone[item.status]}>{item.status}</Badge></td>
            <td className="pr-2 text-right"><div className="text-white">{number(item.last_price, 2)} <span className="text-[10px] text-slate-500">{item.currency}</span></div><div className={`text-[10px] ${item.price_stale ? 'text-amber-400' : 'text-slate-500'}`}>{item.price_stale ? 'STALE · ' : ''}{ago(item.price_as_of)} · {item.price_source || 'n/a'}</div></td>
            <td className={`pr-2 text-right ${chg > 0 ? 'text-emerald-400' : chg < 0 ? 'text-red-400' : 'text-slate-400'}`}>{chg == null ? '-' : `${chg > 0 ? '+' : ''}${number(chg, 2)}%`}</td>
            <td className="pr-2 text-right text-slate-300">{m.rsi14 == null ? '-' : number(m.rsi14, 0)}</td>
            <td className="pr-2 text-slate-300">{zone(item.entry_low, item.entry_high)}</td>
            <td className="pr-2 text-slate-300">{item.target_price ?? <span className="text-slate-600">-</span>}</td>
            <td className="pr-2 text-right text-slate-300">{item.score == null ? '-' : number(item.score, 0)}</td>
            <td className="text-[10px] text-amber-300">{(item.active_conditions || []).map(c => <div key={c}>🔔 {c.replace(`${item.ticker} `, '')}</div>)}</td>
          </tr>
        })}</tbody>
      </table>
      <p className="mt-3 text-[10px] text-slate-500">{payload?.note} Hover a row for its thesis. Costs/fees/tax per idea: GET /api/portfolio/watchlist.</p>
    </div>}
  </Card>
}
