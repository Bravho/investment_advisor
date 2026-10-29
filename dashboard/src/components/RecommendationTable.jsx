import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number, shortDate } from '../utils/format'

const actionTone = { buy: 'green', sell: 'red', hold: 'gray', watch: 'blue', accumulate: 'emerald', reduce: 'red', stop_loss: 'red' }

export default function RecommendationTable({ items = [], loading, error, retry }) {
  items = items || []
  if (loading) return <Skeleton className="h-96" />
  return <Card className="overflow-hidden p-0"><div className="p-5"><SectionTitle title="ประวัติคำแนะนำ" subtitle="Recommendation history" /></div>{error ? <div className="px-5 pb-5"><ServiceError retry={retry} /></div> : !items.length ? <p className="py-16 text-center text-sm text-slate-500">ยังไม่มีประวัติคำแนะนำ</p> : <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-xs"><thead className="border-y border-[#2a2f3e] bg-[#141925] text-slate-500"><tr>{['Date', 'Ticker', 'Action', 'Confidence', 'LLM Model', 'Validated By', 'Outcome', 'Return %'].map(item => <th className="px-4 py-3 font-medium" key={item}>{item}</th>)}</tr></thead><tbody className="divide-y divide-[#2a2f3e]">{items.map(item => {
    const outcome = item.actual_outcome
    return <tr key={item.id} className="hover:bg-white/[0.02]"><td className="px-4 py-4 text-slate-500">{shortDate(item.created_at)}</td><td className="px-4 py-4 font-bold text-white">{item.ticker}</td><td className="px-4 py-4"><Badge tone={actionTone[String(item.action).toLowerCase()]}>{item.action}</Badge></td><td className="px-4 py-4">{number(Number(item.confidence) * (Number(item.confidence) <= 1 ? 100 : 1))}%</td><td className="px-4 py-4 text-slate-400">{item.llm_model || '-'}</td><td className="px-4 py-4 text-slate-400">{Array.isArray(item.validated_by) ? item.validated_by.join(', ') || '-' : item.validated_by || '-'}</td><td className="px-4 py-4">{outcome ? outcome.was_correct ? '✅ Correct' : '❌ Wrong' : '⏳ Pending'}</td><td className={`px-4 py-4 ${Number(outcome?.actual_return_pct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{outcome ? `${number(outcome.actual_return_pct)}%` : '-'}</td></tr>
  })}</tbody></table></div>}</Card>
}
