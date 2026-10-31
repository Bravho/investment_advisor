import { useMemo, useState } from 'react'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-10-31 rewrite: one card per news story, Thai summary first, holdings/watch list first,
// working Bullish/Bearish tabs (sentiment derived from the score; strong_* folded in), daily digest on top.
const TONE = {
  bullish: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  bearish: 'border-red-500/40 bg-red-500/10 text-red-300',
  neutral: 'border-slate-500/40 bg-slate-500/10 text-slate-300',
}
const ICON = { bullish: '▲', bearish: '▼', neutral: '•' }
const Pill = ({ className = '', children, title }) => <span title={title} className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${className}`}>{children}</span>
const when = v => { const d = v ? new Date(v) : null; return d && !isNaN(d) ? d.toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' น.' : '' }
const TABS = [['all', 'ทั้งหมด'], ['bullish', 'ข่าวบวก (Bullish)'], ['bearish', 'ข่าวลบ (Bearish)'], ['portfolio', 'เกี่ยวกับพอร์ต']]

function Digest({ d, counts }) {
  if (!d) return null
  return <div className="mb-4 rounded-xl border border-[#2a2f3e] bg-[#121620] p-4">
    <p className="text-xs font-semibold text-slate-400">สรุปข่าววันนี้ ({d.window_hours} ชม.ล่าสุด)</p>
    <div className="mt-2 flex flex-wrap gap-2 text-xs">
      <Pill className={TONE.bullish}>▲ บวก {d.counts?.bullish ?? 0}</Pill>
      <Pill className={TONE.bearish}>▼ ลบ {d.counts?.bearish ?? 0}</Pill>
      <Pill className={TONE.neutral}>• กลาง {d.counts?.neutral ?? 0}</Pill>
      <Pill className="border-amber-500/40 bg-amber-500/10 text-amber-200">เกี่ยวกับพอร์ต {d.portfolio_related?.stories ?? 0} (บวก {d.portfolio_related?.bullish ?? 0} / ลบ {d.portfolio_related?.bearish ?? 0})</Pill>
      <span className="self-center text-slate-400">โทนตลาด: <b className="text-slate-200">{d.mood_th}</b></span>
      {counts && <span className="self-center text-[10px] text-slate-500">72 ชม.: {counts.total} ข่าว</span>}
    </div>
    <ul className="mt-3 space-y-1.5 text-sm text-slate-200">{(d.takeaways_th || []).map((t, i) => <li key={i}>{t}</li>)}</ul>
  </div>
}

function Story({ item }) {
  const [open, setOpen] = useState(false)
  const hold = new Set(item.holdings_direct || []), wl = new Set(item.watchlist || [])
  const rel = item.tier <= 1 ? 'border-amber-500/40 bg-amber-500/10 text-amber-200' : item.tier === 2 ? 'border-blue-500/40 bg-blue-500/10 text-blue-200' : 'border-slate-600 bg-slate-800/40 text-slate-400'
  return <article className={`rounded-xl border bg-[#121620] p-4 ${item.tier <= 1 ? 'border-amber-500/30' : 'border-[#2a2f3e]'}`}>
    <div className="flex flex-wrap items-center gap-2">
      <Pill className={TONE[item.sentiment]}>{ICON[item.sentiment]} {item.sentiment_th}</Pill>
      <Pill className={item.impact_level === 'high' ? 'border-red-500/30 text-red-200' : item.impact_level === 'medium' ? 'border-amber-500/30 text-amber-200' : 'border-slate-600 text-slate-400'}>{item.impact_th}</Pill>
      <Pill className={rel}>{item.relevance}</Pill>
      <span className="ml-auto text-[11px] text-slate-500">{when(item.published_at)}</span>
    </div>
    <p className="mt-3 text-[15px] leading-relaxed text-white">{item.summary_th}</p>
    {item.why_th && <p className="mt-1.5 text-xs text-slate-300">💡 {item.why_th}</p>}
    <div className="mt-2 flex flex-wrap gap-1.5">{(item.tickers || []).map(t => <span key={t} className={`rounded px-2 py-0.5 text-[11px] font-bold ${hold.has(t) ? 'bg-amber-500/20 text-amber-200' : wl.has(t) ? 'bg-blue-500/20 text-blue-200' : 'bg-slate-700 text-slate-300'}`}>{t.replace('.BK', '')}</span>)}</div>
    <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-slate-500">
      <span className="truncate" title={item.title}>📰 {item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-slate-300">{item.title}</a> : item.title} · {(item.sources || []).join(', ')}</span>
      <button onClick={() => setOpen(!open)} className="shrink-0 rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400 hover:text-slate-200">{open ? 'ซ่อนรายละเอียด' : 'รายละเอียด'}</button>
    </div>
    {open && <div className="mt-2 rounded-lg bg-black/20 p-2 text-[10px] text-slate-500">
      <p>signal: {item.signal} · score {item.score ?? '-'} · confidence {item.confidence ?? '-'} · sentiment model: {item.details?.model || '-'} · summary: {item.summary_status === 'llm' ? item.details?.summary_model : 'template (LLM summary pending)'}</p>
      {(item.details?.tickers_hidden_not_mentioned || []).length > 0 && <p>tickers hidden (not mentioned in the article): {item.details.tickers_hidden_not_mentioned.join(', ')}</p>}
      {(item.topics || []).length > 0 && <p>topics: {item.topics.join(', ')}</p>}
    </div>}
  </article>
}

export default function SentimentFeed({ payload, loading, error, retry, includeCrypto, setIncludeCrypto }) {
  const items = payload?.items || []
  const [filter, setFilter] = useState('all')
  const [ticker, setTicker] = useState('')
  const tickers = useMemo(() => [...new Set(items.flatMap(i => i.tickers || []))].sort(), [items])
  const filtered = useMemo(() => items.filter(i =>
    (filter === 'all' || (filter === 'portfolio' ? i.tier <= 1 : i.sentiment === filter)) && (!ticker || (i.tickers || []).includes(ticker))), [items, filter, ticker])
  const count = k => items.filter(i => k === 'all' ? true : k === 'portfolio' ? i.tier <= 1 : i.sentiment === k).length
  if (loading && !payload) return <Skeleton className="h-[500px]" />
  return <Card>
    <SectionTitle title="ข่าวและสัญญาณล่าสุด" subtitle="สรุปข่าวเป็นภาษาไทย · ข่าวที่เกี่ยวกับพอร์ตและรายการเฝ้าดูขึ้นก่อน · ไม่ใช่คำแนะนำซื้อขาย" />
    {error ? <ServiceError retry={retry} /> : <>
      <Digest d={payload?.digest} counts={payload?.counts_window} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {TABS.map(([k, label]) => <button key={k} onClick={() => setFilter(k)} className={`rounded-lg px-3 py-2 text-xs ${filter === k ? 'bg-blue-500 text-white' : 'bg-[#121620] text-slate-400'}`}>{label} <span className="opacity-70">({count(k)})</span></button>)}
        <select value={ticker} onChange={e => setTicker(e.target.value)} className="rounded-lg border-0 bg-[#121620] px-3 py-2 text-xs text-slate-400 outline-none"><option value="">ทุกหุ้น</option>{tickers.map(t => <option key={t} value={t}>{t}</option>)}</select>
        {setIncludeCrypto && <label className="flex items-center gap-1 text-xs text-slate-500"><input type="checkbox" checked={!!includeCrypto} onChange={e => setIncludeCrypto(e.target.checked)} /> แสดงข่าวคริปโต</label>}
      </div>
      {!filtered.length ? <p className="py-16 text-center text-sm text-slate-500">ไม่มีข่าวในหมวดนี้</p> : <div className="space-y-3">{filtered.map(i => <Story key={i.id} item={i} />)}</div>}
      <p className="mt-3 text-[10px] text-slate-500">ที่มา: news_articles + sentiment_scores (local LLM) · สรุปไทยโดย local LLM (ฟรี) · อัปเดต {when(payload?.generated_at)}</p>
    </>}
  </Card>
}
