import { AlertTriangle, ArrowRightLeft, Bot, Compass, ExternalLink, Lightbulb, Play, Sparkles, Users, WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import StatCard from '../components/StatCard'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from '../components/UI'
import { COUNCIL_API, councilClient } from '../config/api'
import { number } from '../utils/format'

const SCORECARD_URL = `${COUNCIL_API}/`

const SCOPES = [
  { id: 'US equities', label: 'หุ้นสหรัฐ', en: 'US equities' },
  { id: 'Thai SET', label: 'หุ้นไทย SET', en: 'Thai SET' },
  { id: 'Global ETFs / funds', label: 'ETF / กองทุนทั่วโลก', en: 'Global ETFs / funds' },
  { id: 'gold', label: 'ทองคำ', en: 'Gold' },
]

const PROGRESS_STAGES = [
  'AI scout เสนอไอเดียใหม่ตามภาวะตลาด…',
  'ตรวจสอบข้อมูลตลาดจริง (ตัดสิ่งที่ไม่มีข้อมูล)…',
  'สภาที่ปรึกษา 4 มุมมองกำลังให้คะแนน…',
  'เปรียบเทียบกับคู่แข่งและสรุปผล…',
]

const stanceTone = { Buy: 'green', Accumulate: 'emerald', Wait: 'yellow', Caution: 'yellow', Pass: 'red', Unscored: 'gray' }

function LlmBadge({ online, llm }) {
  if (online === false) return <span className="inline-flex items-center gap-2 rounded-full border border-red-500/25 bg-red-500/15 px-3 py-1 text-[11px] font-semibold text-red-300"><WifiOff size={13} /> เซิร์ฟเวอร์ออฟไลน์ · council offline (8993)</span>
  if (!llm) return null
  if (!llm.available) return <Badge tone="yellow">ไม่มีโมเดล AI · no LLM</Badge>
  return <span className="inline-flex items-center gap-2 rounded-full border border-blue-500/25 bg-blue-500/15 px-3 py-1 text-[11px] font-semibold text-blue-300"><Bot size={13} /> {llm.provider} · {llm.model}</span>
}

function ConvictionBar({ value, unscored }) {
  if (unscored) return <span className="text-xs text-slate-500">—</span>
  const tone = value >= 70 ? 'bg-emerald-400' : value >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return <div className="flex items-center gap-2"><div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-700"><div className={`h-full ${tone}`} style={{ width: `${value}%` }} /></div><span className="text-xs tabular-nums text-slate-300">{value}</span></div>
}

function TopIdeas({ ideas }) {
  if (!ideas.length) return <p className="py-12 text-center text-sm text-slate-500">ไม่พบไอเดียใหม่</p>
  return <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-xs">
    <thead className="border-y border-[#2a2f3e] bg-[#141925] text-slate-500"><tr>{['Ticker', 'Theme', 'Verdict', 'Conviction', 'Engine', 'Flags'].map(h => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
    <tbody className="divide-y divide-[#2a2f3e]">{ideas.map(i => <tr key={i.ticker} className="align-top hover:bg-white/[0.02]">
      <td className="px-4 py-4"><p className="font-bold text-white">{i.ticker}</p><p className="text-[11px] text-slate-500">{i.name}</p>{i.price_display && <p className="text-[11px] text-slate-600">{i.price_display}{typeof i.change_pct === 'number' && <span className={i.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}> {i.change_pct >= 0 ? '+' : ''}{number(i.change_pct)}%</span>}</p>}</td>
      <td className="px-4 py-4 text-slate-400">{i.theme || '-'}{i.reason && <p className="mt-1 text-[11px] text-slate-600">{i.reason}</p>}</td>
      <td className="px-4 py-4"><Badge tone={stanceTone[i.stance] || 'gray'}>{i.label || i.stance}</Badge></td>
      <td className="px-4 py-4"><ConvictionBar value={i.conviction} unscored={i.unscored} /></td>
      <td className="px-4 py-4 text-slate-500">{i.llm_used ? 'LLM' : 'no-LLM'}</td>
      <td className="px-4 py-4">{i.flags?.length ? <span className="inline-flex items-center gap-1 text-amber-400"><AlertTriangle size={12} />{i.flags.length}</span> : <span className="text-slate-600">—</span>}</td>
    </tr>)}</tbody>
  </table></div>
}

function Findings({ findings }) {
  const s = findings.stats || {}
  return <div className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="ไอเดียที่พบ" sublabel="Ideas found" value={s.ideas_found || 0} detail={`${s.scored || 0} scored`} icon={Lightbulb} tone="blue" />
      <StatCard label="คะแนนสูงสุด" sublabel="Top conviction" value={`${s.top_conviction || 0}/100`} detail="Highest blended" icon={Sparkles} tone="green" />
      <StatCard label="คะแนนเฉลี่ย" sublabel="Avg conviction" value={`${s.avg_conviction || 0}/100`} detail="Across scored ideas" icon={Compass} tone="yellow" />
      <StatCard label="ภาระภาษี/FX สูง" sublabel="High repatriation drag" value={s.high_drag_count || 0} detail="≥ 2%/yr" icon={ArrowRightLeft} tone="red" />
    </div>

    <Card className="overflow-hidden p-0"><div className="p-5"><SectionTitle title="ไอเดียใหม่เด่น" subtitle="Top new ideas — ranked by council conviction" /></div><TopIdeas ideas={findings.top_ideas || []} /></Card>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <SectionTitle title="คำแนะนำเทียบคู่แข่ง" subtitle="Peer advisories — consider these instead" />
        {findings.peer_advisories?.length ? <ul className="space-y-2">{findings.peer_advisories.map((p, idx) => <li key={`${p.from}-${p.consider}-${idx}`} className="flex items-center gap-3 rounded-xl bg-[#141925] p-3 text-sm">
          <Users size={15} className="shrink-0 text-blue-400" />
          <span className="text-slate-300">For <span className="font-semibold text-white">{p.from}</span>, consider <span className="font-semibold text-emerald-300">{p.consider}</span>{typeof p.score === 'number' && <span className="text-slate-500"> (peer score {number(p.score)})</span>}</span>
        </li>)}</ul> : <p className="py-8 text-center text-sm text-slate-500">ไม่มีคู่แข่งที่ดีกว่าอย่างชัดเจน</p>}
      </Card>

      <Card>
        <SectionTitle title="ภาระจากการนำเงินกลับไทย" subtitle="Repatriation drag (FX + dividend tax)" />
        {findings.repatriation?.length ? <ul className="space-y-2">{findings.repatriation.map((r, idx) => <li key={`${r.ticker}-${idx}`} className="rounded-xl bg-[#141925] p-3 text-sm">
          <div className="flex items-center justify-between"><span className="font-semibold text-white">{r.ticker} <span className="text-[11px] font-normal text-slate-500">{r.origin}</span></span><Badge tone={r.high ? 'red' : 'gray'}>{number(r.total_drag_pct)}%/yr</Badge></div>
          <p className="mt-1 text-[11px] text-slate-500">FX {number(r.fx_drag_pct)}% · dividend {number(r.dividend_drag_pct)}%</p>
          {r.suggestion && <p className="mt-1 text-[11px] text-emerald-400/80">{r.suggestion}</p>}
        </li>)}</ul> : <p className="py-8 text-center text-sm text-slate-500">ไม่มีภาระข้ามพรมแดนที่มีนัยสำคัญ</p>}
      </Card>
    </div>
  </div>
}

export default function Discover() {
  const [scope, setScope] = useState(SCOPES.map(s => s.id))
  const [n, setN] = useState(8)
  const [llm, setLlm] = useState(null)
  const [online, setOnline] = useState(null) // null=checking, true=reachable, false=offline
  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const probe = () => councilClient.get('/api/llm')
    .then(r => { setLlm(r.data); setOnline(true) })
    .catch(() => { setLlm(null); setOnline(false) })

  useEffect(() => { probe() }, [])

  useEffect(() => {
    if (!running) return undefined
    setStage(0)
    const id = window.setInterval(() => setStage(s => Math.min(s + 1, PROGRESS_STAGES.length - 1)), 6000)
    return () => window.clearInterval(id)
  }, [running])

  const toggle = id => setScope(cur => cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id])

  const run = async () => {
    setRunning(true); setError(null); setResult(null)
    try {
      const { data } = await councilClient.post('/api/discover', { scope, n })
      setResult(data); setOnline(true)
      if (data?.llm) setLlm(data.llm)
    } catch (e) { setError(e); setOnline(false) } finally { setRunning(false) }
  }

  const offline = online === false
  const noLlm = online && llm && !llm.available
  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-2xl font-semibold text-white">ค้นหาโอกาสการลงทุน</h2><p className="mt-1 text-sm text-slate-500">Explore / Discover — run the guru council over the data sources</p></div>
      <div className="flex items-center gap-2">
        <LlmBadge online={online} llm={llm} />
        <a href={SCORECARD_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-full border border-[#2a2f3e] bg-[#141925] px-3 py-1 text-[11px] font-semibold text-slate-300 hover:text-white"><ExternalLink size={12} /> Full scorecard</a>
      </div>
    </div>

    <Card>
      <SectionTitle title="ขอบเขตการค้นหา" subtitle="Choose data sources / scope (your holdings are excluded automatically)" />
      <div className="flex flex-wrap gap-2">
        {SCOPES.map(s => { const on = scope.includes(s.id); return <button key={s.id} onClick={() => toggle(s.id)} disabled={running} className={`rounded-xl border px-4 py-2.5 text-left text-xs transition disabled:opacity-50 ${on ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-200' : 'border-[#2a2f3e] bg-[#141925] text-slate-400 hover:text-white'}`}><span className="block text-sm font-medium">{s.label}</span><span className="block text-[10px] opacity-60">{s.en}</span></button> })}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-xs text-slate-400">จำนวนไอเดีย · ideas
          <select value={n} onChange={e => setN(Number(e.target.value))} disabled={running} className="rounded-lg border border-[#2a2f3e] bg-[#141925] px-3 py-2 text-sm text-white disabled:opacity-50">{[4, 6, 8, 10, 12].map(v => <option key={v} value={v}>{v}</option>)}</select>
        </label>
        <button onClick={run} disabled={running || !scope.length || noLlm || offline} className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-[#07140f] transition hover:bg-emerald-400 disabled:opacity-50">
          {running ? <><Sparkles size={16} className="animate-pulse" /> กำลังวิเคราะห์…</> : <><Play size={16} /> Run / Explore</>}
        </button>
      </div>
      {offline && <p className="mt-3 flex items-center gap-2 text-xs text-red-400"><WifiOff size={13} /> เชื่อมต่อ Guru Council (พอร์ต 8993) ไม่ได้ — เริ่มเซิร์ฟเวอร์ด้วย <code className="rounded bg-black/30 px-1">python3 -m guru_council.cli serve</code> หรือ <code className="rounded bg-black/30 px-1">bash start_all.sh</code> · <button onClick={probe} className="underline">ลองใหม่</button></p>}
      {noLlm && <p className="mt-3 flex items-center gap-2 text-xs text-amber-400"><AlertTriangle size={13} /> ต้องตั้งค่าโมเดล AI (OpenAI/Anthropic) ก่อนจึงจะค้นหาไอเดียใหม่ได้ — Discovery requires an LLM.</p>}
    </Card>

    {running && <Card><div className="flex items-center gap-3"><Sparkles size={18} className="animate-pulse text-emerald-400" /><div className="flex-1"><p className="text-sm text-slate-300">{PROGRESS_STAGES[stage]}</p><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-700"><div className="h-full bg-emerald-400 transition-all duration-700" style={{ width: `${((stage + 1) / PROGRESS_STAGES.length) * 100}%` }} /></div></div></div><Skeleton className="mt-5 h-40" /></Card>}

    {error && <ServiceError retry={run} />}

    {result && !running && (result.available ? <Findings findings={result.findings || {}} /> : <Card><div className="flex items-center gap-3 text-amber-400"><AlertTriangle size={18} /><p className="text-sm">{result.reason || 'Scout unavailable — configure an LLM and retry.'}</p></div></Card>)}

    <p className="text-[11px] leading-5 text-slate-600">⚠️ ข้อมูลนี้เป็นการวิเคราะห์เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน และไม่มีการซื้อขายอัตโนมัติ · ตัวเลขภาษีเป็นเพียง “ค่าประมาณ” โปรดยืนยันกับผู้เชี่ยวชาญด้านภาษีไทย · For research only — not financial advice. No auto-trading. Tax figures are estimates.</p>
  </div>
}
