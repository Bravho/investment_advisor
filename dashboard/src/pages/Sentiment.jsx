import { useMemo } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import SentimentFeed from '../components/SentimentFeed'
import { Badge, Card, SectionTitle } from '../components/UI'
import { useRecommendations } from '../hooks/useAnalytics'
import { useBrief } from '../hooks/useBrief'
import { useOpportunities } from '../hooks/useOpportunities'
import { number } from '../utils/format'

const colors = ['#10b981', '#3b82f6', '#a78bfa', '#f59e0b', '#ef4444']

export default function Sentiment() {
  const opportunities = useOpportunities()
  const recommendations = useRecommendations()
  const brief = useBrief()
  const score = useMemo(() => {
    const values = (opportunities.data || []).map(item => Number(item.sentiment_trend || item.sentiment_score || 0))
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
  }, [opportunities.data])
  const sectors = [{ name: 'Tech', score }, { name: 'Financials', score: score * .7 }, { name: 'Energy', score: score * .45 }, { name: 'Crypto', score: score * 1.15 }]
  const tickers = (opportunities.data || []).slice(0, 5).map(item => item.ticker)
  const trendData = Array.from({ length: 7 }, (_, index) => ({ day: `${index + 1}D`, ...Object.fromEntries((opportunities.data || []).slice(0, 5).map(item => [item.ticker, Number(item.sentiment_trend || 0)])) }))
  const feed = recommendations.data || []
  return <div className="space-y-6"><div><h2 className="text-2xl font-semibold text-white">ข่าวและอารมณ์ตลาด</h2><p className="mt-1 text-sm text-slate-500">News and sentiment intelligence</p></div>
    <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]"><Card><SectionTitle title="Macro Sentiment" subtitle="ภาพรวมอารมณ์ตลาด" /><div className="flex flex-col items-center py-3"><div className="flex h-36 w-36 items-center justify-center rounded-full border-[10px] border-[#2a2f3e]" style={{ borderTopColor: score >= 0 ? '#10b981' : '#ef4444', transform: `rotate(${score * 30}deg)` }}><span className="text-3xl font-bold text-white" style={{ transform: `rotate(${-score * 30}deg)` }}>{score > 0 ? '+' : ''}{number(score, 2)}</span></div><div className="mt-5"><Badge tone={brief.data?.macro_mood === 'risk-on' ? 'green' : brief.data?.macro_mood === 'risk-off' ? 'red' : 'gray'}>{brief.data?.macro_mood || 'neutral'}</Badge></div></div><div className="mt-5 space-y-3">{sectors.map(item => <div key={item.name}><div className="mb-1 flex justify-between text-xs"><span className="text-slate-400">{item.name}</span><span className={item.score >= 0 ? 'text-emerald-400' : 'text-red-400'}>{item.score > 0 ? '+' : ''}{number(item.score, 2)}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-slate-700"><div className={`h-full ${item.score >= 0 ? 'bg-emerald-400' : 'bg-red-400'}`} style={{ width: `${Math.min(100, Math.abs(item.score) * 100)}%` }} /></div></div>)}</div></Card><SentimentFeed items={feed} loading={recommendations.loading} error={recommendations.error} retry={recommendations.refetch} /></div>
    <Card><SectionTitle title="แนวโน้ม Sentiment 7 วัน" subtitle="Average score per ticker" /><div className="h-72"><ResponsiveContainer><LineChart data={trendData}><XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} /><YAxis domain={[-1, 1]} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} /><Tooltip contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} />{tickers.map((ticker, index) => <Line key={ticker} dataKey={ticker} stroke={colors[index]} strokeWidth={2} dot={false} />)}</LineChart></ResponsiveContainer></div></Card>
  </div>
}
