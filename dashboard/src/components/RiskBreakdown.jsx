import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { normalizeRisk, number, valueOf } from '../utils/format'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

const color = score => score < 33 ? '#10b981' : score < 66 ? '#f59e0b' : '#ef4444'

export default function RiskBreakdown({ risk, holdings = [], loading, error, retry }) {
  holdings = holdings || []
  if (loading) return <Skeleton className="h-96" />
  const overall = normalizeRisk(valueOf(risk, ['portfolio_risk_score', 'risk_score']))
  const data = (risk?.holdings || risk?.risk_breakdown || holdings).map(item => {
    const fallback = Math.min(100, 25 + Math.abs(Number(valueOf(item, ['unrealized_pnl_pct', 'pnl_pct']))) * 2)
    return { ticker: item.ticker, score: normalizeRisk(valueOf(item, ['risk_score', 'score'], fallback)) }
  })
  return <Card><SectionTitle title="โครงสร้างความเสี่ยง" subtitle="Risk score by holding" />{error ? <ServiceError retry={retry} /> : <><div className="h-56"><ResponsiveContainer><BarChart data={data} layout="vertical" margin={{ left: 5 }}><XAxis type="number" domain={[0, 100]} hide /><YAxis type="category" dataKey="ticker" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} width={55} /><Tooltip cursor={{ fill: '#ffffff05' }} contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} /><Bar dataKey="score" radius={[0, 6, 6, 0]}>{data.map(item => <Cell key={item.ticker} fill={color(item.score)} />)}</Bar></BarChart></ResponsiveContainer></div><div className="mt-5 flex items-center gap-5 rounded-xl bg-[#121620] p-4"><div className="relative h-20 w-20 rounded-full" style={{ background: `conic-gradient(${color(overall)} ${overall * 3.6}deg, #2a2f3e 0deg)` }}><div className="absolute inset-2 flex items-center justify-center rounded-full bg-[#121620] text-lg font-bold text-white">{number(overall, 0)}</div></div><div><p className="font-medium text-white">Overall risk score</p><p className="mt-1 text-xs text-slate-500">คะแนนความเสี่ยงรวมของพอร์ต</p></div></div></>}</Card>
}
