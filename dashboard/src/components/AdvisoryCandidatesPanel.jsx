import { useMemo, useState } from 'react'
import { Badge, Card, SectionTitle } from './UI'
import { number } from '../utils/format'
import { X } from 'lucide-react'

const signalTone = {
  strong_bullish: 'emerald',
  bullish: 'blue',
  neutral: 'gray',
  bearish: 'yellow',
  strong_bearish: 'red',
}

export default function AdvisoryCandidatesPanel({ payload, loading, error, retry }) {
  const [selected, setSelected] = useState(null)
  const candidates = payload?.candidates || []
  const sorted = useMemo(
    () => [...candidates].sort((a, b) => Number(b.rank_score || b.opportunity_score || 0) - Number(a.rank_score || a.opportunity_score || 0)),
    [candidates],
  )
  return (
    <Card>
      <SectionTitle
        title="Advisory candidates"
        subtitle="News → ticker ranked suggestions (advisory only — no auto-trade)"
        action={retry ? <button onClick={retry} className="text-[11px] text-slate-400 hover:text-white">Refresh</button> : null}
      />
      {loading && <p className="py-6 text-center text-xs text-slate-500">Loading advisory candidates...</p>}
      {error && <p className="py-6 text-center text-xs text-red-400">Advisory endpoint unavailable</p>}
      {!loading && !error && !sorted.length && <p className="py-6 text-center text-xs text-slate-500">No advisory candidates in lookback window</p>}
      <div className="space-y-2">
        {sorted.slice(0, 8).map(item => (
          <button key={item.ticker} onClick={() => setSelected(item)} className="w-full rounded-xl border border-transparent bg-[#141925] p-3 text-left transition hover:border-amber-500/30">
            <div className="flex items-center justify-between">
              <span className="rounded-lg bg-slate-700/60 px-2 py-1 text-xs font-bold text-white">{item.ticker}</span>
              <div className="flex items-center gap-2">
                <Badge tone="yellow">advisory</Badge>
                <Badge tone={signalTone[item.sentiment_signal] || signalTone[item.signal] || 'gray'}>{item.sentiment_signal || item.signal}</Badge>
              </div>
            </div>
            <p className="mt-2 line-clamp-2 text-[11px] text-slate-400">{item.latest_headline || '—'}</p>
            <div className="mt-3 flex items-center gap-3">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-700">
                <div className="h-full rounded-full bg-gradient-to-r from-amber-500 to-emerald-400" style={{ width: `${Math.min(100, Number(item.rank_score || item.opportunity_score) || 0)}%` }} />
              </div>
              <span className="w-9 text-right text-xs font-semibold text-white">{number(item.rank_score || item.opportunity_score, 0)}</span>
            </div>
            <div className="mt-2 flex justify-between text-[10px] text-slate-500">
              <span>{item.article_count || 0} articles</span>
              <span>{item.suggested_action}</span>
            </div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4" onClick={() => setSelected(null)}>
          <Card className="w-full max-w-lg" onClick={event => event.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <p className="text-2xl font-bold text-white">{selected.ticker}</p>
                <Badge tone="yellow">advisory only · not actionable</Badge>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white"><X /></button>
            </div>
            <p className="mt-4 text-sm text-slate-300">{selected.latest_headline}</p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {[
                ['Rank score', number(selected.rank_score || selected.opportunity_score)],
                ['Confidence', number(Number(selected.confidence) * 100, 0) + '%'],
                ['Sentiment', selected.sentiment_signal],
                ['Impact', selected.impact_level],
                ['Articles', selected.article_count],
                ['Suggested', selected.suggested_action],
              ].map(([key, value]) => (
                <div key={key} className="rounded-xl bg-[#121620] p-3">
                  <p className="text-[10px] uppercase text-slate-500">{key}</p>
                  <p className="mt-1 text-sm font-medium text-white">{value || '-'}</p>
                </div>
              ))}
            </div>
            <p className="mt-5 text-[11px] text-slate-500">Human approval required before treating as actionable. No auto-trade.</p>
          </Card>
        </div>
      )}
    </Card>
  )
}
