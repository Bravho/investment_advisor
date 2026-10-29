import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { portfolioClient } from '../config/api'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'

const moodTone = { 'risk-on': 'green', 'risk-off': 'red', neutral: 'gray' }

export default function BriefPanel({ brief, loading, error, retry }) {
  const [regenerating, setRegenerating] = useState(false)
  let actionItems = brief?.action_items
  if (typeof actionItems === 'string') {
    try { actionItems = JSON.parse(actionItems) } catch { actionItems = [actionItems] }
  }
  if (!Array.isArray(actionItems)) actionItems = []
  const regenerate = async () => {
    setRegenerating(true)
    try { await portfolioClient.get('/brief/today'); await retry() } finally { setRegenerating(false) }
  }
  if (loading) return <Skeleton className="h-72" />
  return <Card><SectionTitle title="สรุปตลาดวันนี้" subtitle="Daily intelligence brief" action={<button onClick={regenerate} disabled={regenerating} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-[#07140f] disabled:opacity-50"><RefreshCw size={13} className={regenerating ? 'animate-spin' : ''} /> Regenerate</button>} />
    {error ? <ServiceError retry={retry} /> : <><div className="mb-5 flex flex-wrap items-center gap-3"><Badge tone={moodTone[brief?.macro_mood]}>{brief?.macro_mood || 'unknown'}</Badge><span className="text-xs text-slate-500">{brief?.brief_date || 'Today'}</span></div><div className="prose prose-invert max-w-none text-sm leading-7 text-slate-300"><ReactMarkdown>{brief?.content || 'ยังไม่มีสรุปตลาดวันนี้'}</ReactMarkdown></div>{actionItems.length > 0 && <div className="mt-6 border-t border-[#2a2f3e] pt-5"><p className="mb-3 text-xs font-semibold uppercase tracking-wider text-emerald-400">Action items</p><ol className="space-y-2">{actionItems.map((item, index) => <li key={`${item}-${index}`} className="flex gap-3 rounded-xl bg-[#141925] p-3 text-sm text-slate-300"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-[10px] font-bold text-emerald-400">{index + 1}</span>{item}</li>)}</ol></div>}</>}
  </Card>
}
