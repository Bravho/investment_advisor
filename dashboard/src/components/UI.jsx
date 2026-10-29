import { AlertCircle, RefreshCw } from 'lucide-react'

export const Card = ({ children, className = '', ...props }) => (
  <section className={`rounded-2xl border border-[#2a2f3e] bg-[#1a1f2e] p-5 shadow-xl shadow-black/10 ${className}`} {...props}>{children}</section>
)

export const SectionTitle = ({ title, subtitle, action }) => (
  <div className="mb-5 flex items-start justify-between gap-3">
    <div><h2 className="text-lg font-semibold text-white">{title}</h2>{subtitle && <p className="mt-1 text-xs text-slate-400">{subtitle}</p>}</div>
    {action}
  </div>
)

export const Skeleton = ({ className = 'h-24' }) => <div className={`animate-pulse rounded-xl bg-slate-700/50 ${className}`} />

export const ServiceError = ({ retry, compact = false }) => (
  <div className={`flex flex-col items-center justify-center rounded-xl border border-red-500/20 bg-red-500/5 text-center ${compact ? 'p-4' : 'min-h-40 p-8'}`}>
    <AlertCircle className="mb-2 text-red-400" size={22} />
    <p className="font-medium text-red-300">Service unavailable</p>
    <p className="mt-1 text-xs text-slate-500">ไม่สามารถเชื่อมต่อบริการได้</p>
    <button onClick={retry} className="mt-3 flex items-center gap-2 rounded-lg bg-slate-700 px-3 py-2 text-xs text-white hover:bg-slate-600"><RefreshCw size={13} /> Retry</button>
  </div>
)

export const Badge = ({ children, tone = 'gray' }) => {
  const tones = {
    green: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
    blue: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
    red: 'bg-red-500/15 text-red-300 border-red-500/25',
    yellow: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
    gray: 'bg-slate-500/15 text-slate-300 border-slate-500/25',
  }
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${tones[tone] || tones.gray}`}>{children}</span>
}

// 2026-10-30: data-source + timestamp badge with a stale flag. `asOf` = ISO string/date; staleHours = threshold.
export const SourceBadge = ({ source, asOf, staleHours = 26 }) => {
  if (!source && !asOf) return null
  const t = asOf ? new Date(asOf) : null
  const valid = t && !isNaN(t)
  const ageH = valid ? (Date.now() - t.getTime()) / 3.6e6 : null
  const stale = ageH != null && ageH > staleHours
  const when = valid ? t.toLocaleString('en-GB', { timeZone: 'Asia/Bangkok', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' ICT' : (asOf || 'time n/a')
  return <span title={`source: ${source || 'n/a'} · as of ${when}${stale ? ` · STALE (> ${staleHours}h)` : ''}`}
    className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${stale ? 'border-red-500/50 bg-red-500/10 text-red-300' : 'border-slate-700 bg-slate-800/60 text-slate-400'}`}>
    {source && <span>{source}</span>}<span>· {when}</span>{stale && <b>STALE</b>}
  </span>
}
