import { TrendingDown, TrendingUp, WalletCards } from 'lucide-react'
import { money, number, valueOf } from '../utils/format'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

export default function HoldingsTable({ holdings = [], loading, error, retry }) {
  holdings = holdings || []
  if (loading) return <Skeleton className="h-80" />
  return <Card className="overflow-hidden p-0">
    <div className="p-5"><SectionTitle title="สินทรัพย์ในพอร์ต" subtitle="Portfolio holdings" /></div>
    {error ? <div className="px-5 pb-5"><ServiceError retry={retry} /></div> : !holdings.length ? <div className="flex min-h-56 flex-col items-center justify-center px-5 pb-8 text-center"><WalletCards size={32} className="mb-3 text-slate-600" /><p className="text-sm text-slate-300">Add holdings via psql to see your portfolio</p><p className="mt-1 text-xs text-slate-600">เพิ่มสินทรัพย์ผ่านฐานข้อมูลเพื่อเริ่มติดตามพอร์ต</p></div> :
    <div className="overflow-x-auto"><table className="w-full min-w-[940px] text-left text-xs"><thead className="border-y border-[#2a2f3e] bg-[#141925] text-slate-500"><tr>{['Ticker', 'Name', 'Qty', 'Avg Cost', 'Current Price', 'Market Value (THB)', 'P&L (THB)', 'P&L%', 'Trend'].map(x => <th key={x} className="px-4 py-3 font-medium">{x}</th>)}</tr></thead><tbody className="divide-y divide-[#2a2f3e]">{holdings.map(item => {
      const pnl = Number(valueOf(item, ['pnl_thb', 'unrealized_pnl_thb']))
      const pnlPct = Number(valueOf(item, ['pnl_pct', 'unrealized_pnl_pct']))
      const price = valueOf(item, ['current_price', 'live_price'])
      const positive = pnl >= 0
      return <tr key={item.ticker} className="hover:bg-white/[0.02]"><td className="px-4 py-4 font-bold text-white">{item.ticker}</td><td className="max-w-56 px-4 py-4 text-slate-400"><div className="truncate" title={item.name}>{item.name || '-'}</div>{item.tax_wrapper && <div className="mt-1 flex flex-wrap gap-1" title={item.lock_note || ''}><span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] text-sky-300">{item.tax_wrapper}</span>{item.locked && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">🔒 until {item.lock_until}</span>}{item.units_status === 'pending' && <span className="rounded bg-slate-500/20 px-1.5 py-0.5 text-[10px] text-slate-300">units pending · {money(item.amount_invested_thb)} invested</span>}</div>}</td><td className="px-4 py-4">{item.units_status === 'pending' ? <span className="text-amber-300" title={item.valuation_basis || ''}>pending</span> : number(item.quantity, 4)}</td><td className="px-4 py-4">{money(item.avg_cost_price)}</td><td className="px-4 py-4">{money(price)}</td><td className="px-4 py-4 font-medium text-white" title={item.valuation_basis || ''}>{money(item.market_value_thb)}{item.is_estimated && <span className="ml-1 text-[10px] text-amber-300">est.</span>}</td><td className={`px-4 py-4 font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{money(pnl)}</td><td className={`px-4 py-4 ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{pnlPct >= 0 ? '+' : ''}{number(pnlPct)}%</td><td className={`px-4 py-4 ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{positive ? <TrendingUp size={17} /> : <TrendingDown size={17} />}</td></tr>
    })}</tbody></table></div>}
  </Card>
}
