import { useMemo, useState } from 'react'
import { shortDate, time, valueOf } from '../utils/format'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'

const sentimentOf = item => String(valueOf(item, ['sentiment', 'sentiment_label'], item.sentiment_snapshot?.score > 0.2 ? 'bullish' : item.sentiment_snapshot?.score < -0.2 ? 'bearish' : 'neutral')).toLowerCase()

export default function SentimentFeed({ items = [], loading, error, retry }) {
  items = items || []
  const [filter, setFilter] = useState('all')
  const [ticker, setTicker] = useState('')
  const tickers = [...new Set(items.map(item => item.ticker).filter(Boolean))]
  const filtered = useMemo(() => items.filter(item => (filter === 'all' || sentimentOf(item) === filter) && (!ticker || item.ticker === ticker)), [items, filter, ticker])
  if (loading) return <Skeleton className="h-[500px]" />
  return <Card><SectionTitle title="ข่าวและสัญญาณล่าสุด" subtitle="News sentiment feed" /><div className="mb-5 flex flex-wrap gap-2">{['all', 'bullish', 'bearish'].map(value => <button key={value} onClick={() => setFilter(value)} className={`rounded-lg px-3 py-2 text-xs capitalize ${filter === value ? 'bg-blue-500 text-white' : 'bg-[#121620] text-slate-400'}`}>{value}</button>)}<select value={ticker} onChange={event => setTicker(event.target.value)} className="rounded-lg border-0 bg-[#121620] px-3 py-2 text-xs text-slate-400 outline-none"><option value="">All tickers</option>{tickers.map(item => <option key={item}>{item}</option>)}</select></div>
    {error ? <ServiceError retry={retry} /> : !filtered.length ? <p className="py-16 text-center text-sm text-slate-500">ยังไม่มีข้อมูลข่าวหรือ sentiment</p> : <div className="space-y-3">{filtered.map((item, index) => {
      const sentiment = sentimentOf(item)
      const tone = sentiment === 'bullish' ? 'green' : sentiment === 'bearish' ? 'red' : 'gray'
      const impact = String(item.impact_level || (Number(item.confidence) > 0.75 ? 'high' : 'medium')).toLowerCase()
      return <article key={item.id || index} className="rounded-xl border border-[#2a2f3e] bg-[#121620] p-4"><div className="flex flex-wrap items-center gap-2"><Badge tone="blue">{item.source || item.llm_model || 'AI signal'}</Badge><Badge tone={tone}>{sentiment} {item.sentiment_snapshot?.score ?? ''}</Badge><Badge tone={impact === 'high' ? 'red' : impact === 'medium' ? 'yellow' : 'gray'}>{impact} impact</Badge></div><h3 className="mt-3 font-medium text-white">{item.title || item.rationale || `${item.action || 'Watch'} signal for ${item.ticker}`}</h3><div className="mt-3 flex items-center justify-between text-[10px] text-slate-500"><span>{item.ticker && <span className="rounded bg-slate-700 px-2 py-1 font-bold text-slate-300">{item.ticker}</span>}</span><span>{shortDate(item.published_at || item.created_at)} · {time(item.published_at || item.created_at)}</span></div></article>
    })}</div>}
  </Card>
}
