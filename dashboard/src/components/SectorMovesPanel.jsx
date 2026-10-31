import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-10-31: replaces the old Macro Sentiment gauge + sector bars (they were score x fixed multipliers, not data).
const thDate = s => { if (!s) return ''; const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) }
const pct = v => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

export default function SectorMovesPanel({ data, loading, error, retry, digest }) {
  if (loading && !data) return <Skeleton className="h-[420px]" />
  return <Card>
    <SectionTitle title="หมวดที่กระทบพอร์ต" subtitle="เดือนที่ผ่านมาเปลี่ยนไปเท่าไร และมีข่าวอะไร" />
    {digest && <div className="mb-3 rounded-lg bg-[#121620] p-3 text-xs text-slate-300" title="นับจำนวนข่าวที่ระบบวิเคราะห์ใน 24 ชั่วโมงล่าสุด แยกตามโทนข่าว">
      โทนข่าว 24 ชม.: <span className="text-emerald-300">บวก {digest.counts?.bullish ?? 0}</span> · <span className="text-red-300">ลบ {digest.counts?.bearish ?? 0}</span> · กลาง {digest.counts?.neutral ?? 0}
      <span className="text-slate-500"> (รวม {digest.stories} ข่าว · ภาพรวม{digest.mood_th})</span>
    </div>}
    {error ? <ServiceError retry={retry} /> : <div className="space-y-2.5">
      {(data?.lines || []).map(l => {
        const up = l.direction === 'up', down = l.direction === 'down'
        return <div key={l.key} className="rounded-lg border border-[#2a2f3e] bg-[#121620] p-3">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-sm font-semibold text-white">{l.name_th}{l.holding && <span className="ml-1.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-normal text-amber-200">{l.holding}</span>}</p>
            {l.change_1m_pct === null || l.change_1m_pct === undefined
              ? <span className="text-sm text-amber-300">unknown</span>
              : <span className={`text-base font-bold ${up ? 'text-emerald-300' : down ? 'text-red-300' : 'text-slate-300'}`}>{up ? '▲' : down ? '▼' : '◆'} {pct(l.change_1m_pct)}</span>}
          </div>
          <p className="text-[10px] text-slate-500">{l.proxy_th} · 1 เดือน ({thDate(l.from_date)} → {thDate(l.as_of)})</p>
          {l.news?.title && <p className="mt-1.5 text-[11px] leading-relaxed text-slate-300">📰 {l.news.line_th
            ? l.news.line_th
            : <a href={l.news.url} target="_blank" rel="noreferrer" className="hover:text-white">{l.news.title}</a>}
            <span className="text-slate-500"> ({thDate(l.news.published_at)})</span></p>}
          {l.news?.title && l.news.line_th && <a href={l.news.url} target="_blank" rel="noreferrer" className="mt-0.5 block truncate text-[10px] text-slate-500 hover:text-slate-300" title={l.news.title}>ต้นฉบับ: {l.news.title}</a>}
          {l.news && !l.news.title && <p className="mt-1.5 text-[10px] text-slate-500">ไม่มีข่าวที่พูดถึงหมวดนี้โดยตรงใน 7 วัน</p>}
        </div>
      })}
      <p className="pt-1 text-[10px] leading-relaxed text-slate-500" title={data?.method_th}>ⓘ {data?.method_th}</p>
    </div>}
  </Card>
}
