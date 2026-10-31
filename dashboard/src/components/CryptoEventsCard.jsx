import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-11-01: ONLY high-impact crypto events (regulation, ETF approvals/flows, exchange hacks/collapses,
// stablecoin de-pegs, state reserves, mega-liquidations, large BTC moves/regime breaks). Display-only:
// crypto is excluded from the market-mood verdict and from signals.
const thDT = s => { if (!s) return ''; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }
const trig = { '1d': 'BTC เคลื่อนแรงใน 1 วัน', '7d': 'BTC เคลื่อนแรงใน 7 วัน', sma200: 'BTC ตัดเส้นเฉลี่ย 200 วัน' }
const pct = v => (v === null || v === undefined ? 'unknown' : `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`)

export default function CryptoEventsCard({ data, loading, error, retry }) {
  if (loading && !data) return <Skeleton className="h-40" />
  const cards = data?.cards || []
  return <Card>
    <SectionTitle title="เหตุการณ์คริปโตสำคัญ" subtitle="แยกจากอารมณ์ตลาดหลัก · ไม่ใช้ใน signals · 72 ชม. ล่าสุด" />
    {error ? <ServiceError retry={retry} compact /> : !cards.length
      ? <p className="rounded-lg bg-[#121620] p-4 text-center text-sm text-slate-400">{data?.empty_text_th || 'ไม่มีเหตุการณ์สำคัญ'}</p>
      : <div className="space-y-2.5">{cards.map((c, i) => <div key={i} className="rounded-lg border border-[#2a2f3e] bg-[#121620] p-3">
        {c.type === 'news' ? <>
          <div className="flex items-baseline justify-between gap-2">
            <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[11px] text-violet-200">{c.category_th}</span>
            <span className={`text-xs font-semibold ${c.direction === 'ลบ' ? 'text-red-300' : 'text-emerald-300'}`}>โทน{c.direction} · {c.n_sources} แหล่ง</span>
          </div>
          <a href={c.url} target="_blank" rel="noreferrer" className="mt-1.5 block text-sm font-medium text-white hover:underline">{c.headline}</a>
          <p className="mt-1 text-[10px] text-slate-500">{thDT(c.at)} · {(c.headlines || []).map(h => h.source).filter((v, j, a) => a.indexOf(v) === j).join(', ')}</p>
        </> : <>
          <div className="flex items-baseline justify-between gap-2">
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-200">ราคา BTC</span>
            <span className="text-[10px] text-slate-500">{thDT(c.at)}</span>
          </div>
          {(c.triggers || [c]).map((t, j) => <p key={j} className="mt-1.5 text-sm text-white">{trig[t.trigger] || t.trigger}: <span className={t.value_pct < 0 ? 'text-red-300' : 'text-emerald-300'}>{pct(t.value_pct)}</span> <span className="text-[10px] text-slate-500">(เกณฑ์ {t.threshold})</span></p>)}
          {c.related_news && <p className="mt-1 text-[11px] text-slate-400">📰 <a href={c.related_news.url} target="_blank" rel="noreferrer" className="hover:text-white">{c.related_news.title}</a> <span className="text-slate-500">— {c.related_news.note}</span></p>}
        </>}
      </div>)}</div>}
    {data?.rule_th && <p className="mt-3 text-[10px] leading-relaxed text-slate-500">เกณฑ์: {data.rule_th}</p>}
  </Card>
}
