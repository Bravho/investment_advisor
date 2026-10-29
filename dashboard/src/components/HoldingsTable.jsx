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
      return <tr key={item.ticker} className="hover:bg-white/[0.02]"><td className="px-4 py-4 font-bold text-white">{item.ticker}</td><td className="max-w-36 truncate px-4 py-4 text-slate-400">{item.name || '-'}</td><td className="px-4 py-4">{number(item.quantity, 4)}</td><td className="px-4 py-4">{money(item.avg_cost_price)}</td><td className="px-4 py-4">{money(price)}</td><td className="px-4 py-4 font-medium text-white">{money(item.market_value_thb)}</td><td className={`px-4 py-4 font-medium ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{money(pnl)}</td><td className={`px-4 py-4 ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{pnlPct >= 0 ? '+' : ''}{number(pnlPct)}%</td><td className={`px-4 py-4 ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{positive ? <TrendingUp size={17} /> : <TrendingDown size={17} />}</td></tr>
    })}</tbody></table></div>}
  </Card>
}
