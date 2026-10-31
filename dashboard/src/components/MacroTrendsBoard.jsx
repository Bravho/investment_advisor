import { Fragment, useState } from 'react'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-10-31: 'แนวโน้มตัวชี้วัดสำคัญ' - frozen, scored forecasts for key macro indicators + official policy rates.
const DIR = {
  up: { icon: '▲', cls: 'text-emerald-300', bg: 'bg-emerald-500/10 border-emerald-500/30' },
  down: { icon: '▼', cls: 'text-red-300', bg: 'bg-red-500/10 border-red-500/30' },
  flat: { icon: '◆', cls: 'text-slate-300', bg: 'bg-slate-500/10 border-slate-500/30' },
}
const CONF_CLS = { low: 'text-slate-500', medium: 'text-amber-300', high: 'text-emerald-300' }
const HZ_TH = { '3d': '3 วัน', '1m': '1 เดือน', '3m': '3 เดือน', '6m': '6 เดือน', '1y': '1 ปี' }
const PATH = { hold: 'text-slate-200 bg-slate-500/15 border-slate-500/40', cut: 'text-emerald-200 bg-emerald-500/15 border-emerald-500/40', hike: 'text-red-200 bg-red-500/15 border-red-500/40' }

const fmt = (v, rate) => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return 'unknown'
  const n = Number(v), a = Math.abs(n)
  if (rate) return n.toFixed(2)
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : 3
  return n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
}
const chg = (v, basis) => v === null || v === undefined ? '–' : basis === 'pp' ? `${v > 0 ? '+' : ''}${(v * 100).toFixed(0)} bp` : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
const pct = v => v === null || v === undefined ? '–' : `${Math.round(v * 100)}%`
const thDate = s => { if (!s) return 'unknown'; const d = new Date(s.length === 7 ? `${s}-01` : s); return isNaN(d) ? s : d.toLocaleDateString('th-TH', { day: s.length === 7 ? undefined : 'numeric', month: 'short', year: 'numeric' }) }

function Spark({ data, up }) {
  if (!data || data.length < 2) return <div className="h-8 w-28 text-[10px] text-slate-600">ไม่มีกราฟ</div>
  const min = Math.min(...data), max = Math.max(...data), w = 112, h = 30
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 2) - 1}`).join(' ')
  return <svg width={w} height={h} className="shrink-0"><polyline points={pts} fill="none" stroke={up ? '#34d399' : '#f87171'} strokeWidth="1.5" /></svg>
}

function HCell({ x, rate }) {
  if (!x || !x.direction) return <div className="rounded-lg border border-slate-700/50 px-2 py-1.5 text-center text-[10px] text-slate-600">ยังไม่มี</div>
  const d = DIR[x.direction]
  return <div className={`rounded-lg border px-2 py-1.5 text-center ${d.bg}`} title={x.reason_th}>
    <div className={`text-xs font-semibold ${d.cls}`}>{d.icon} {x.direction_th} <span className="font-normal opacity-70">{Math.round(x.p_up * 100)}%</span></div>
    <div className="mt-0.5 text-[10px] text-slate-300">{x.scaled_from_proxy ? '≈' : ''}{fmt(x.low80, rate)}–{fmt(x.high80, rate)}</div>
    <div className={`text-[10px] ${CONF_CLS[x.confidence_lvl]}`}>มั่นใจ{x.confidence_th}</div>
  </div>
}

function Detail({ c }) {
  return <div className="mt-3 space-y-3 rounded-lg bg-black/25 p-3 text-[11px] text-slate-400">
    {c.proxy_th && <p className="text-amber-200/90">⚠️ ตัวแทน (proxy): {c.proxy_th}</p>}
    {c.note_th && <p>หมายเหตุ: {c.note_th}</p>}
    <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left">
      <thead className="text-slate-500"><tr><th className="py-1">ระยะ</th><th>P(ขึ้น)</th><th>ค่ากลาง</th><th>ช่วง 50%</th><th>ช่วง 80%</th><th>ครบกำหนด</th><th>เหตุผล</th><th>ความแม่นยำ</th></tr></thead>
      <tbody>{(c.horizons || []).filter(x => x.direction).map(x => <tr key={x.horizon} className="border-t border-slate-800 align-top">
        <td className="py-1 text-slate-300">{HZ_TH[x.horizon]}</td><td>{Math.round(x.p_up * 100)}%</td><td>{fmt(x.median, c.is_rate)}</td>
        <td>{fmt(x.low50, c.is_rate)}–{fmt(x.high50, c.is_rate)}</td><td>{fmt(x.low80, c.is_rate)}–{fmt(x.high80, c.is_rate)}</td><td>{thDate(x.target_date)}</td>
        <td className="max-w-[220px]">{x.reason_th}</td>
        <td><span className={x.live_track ? 'text-slate-200' : 'text-amber-300'}>{x.validation_th}</span>
          {x.backtest_track && <div className="text-slate-500">ย้อนหลัง: ทิศถูก {pct(x.backtest_track.hit)} · อยู่ในช่วง 80% {pct(x.backtest_track.cov80)} (n={x.backtest_track.n})</div>}</td>
      </tr>)}</tbody></table></div>
    {(() => { const x = (c.horizons || []).find(h => h.horizon === '1m' && h.models); return x ? <div>
      <p className="font-semibold text-slate-300">วิธีคำนวณ (ตัวอย่าง 1 เดือน)</p>
      <p>ค่าเฉลี่ยถ่วงน้ำหนักของโมเดล: {Object.entries(x.models).filter(([k, v]) => v !== null && x.weights?.[k]).map(([k, v]) => `${k} ${(v * 100).toFixed(2)}% (น้ำหนัก ${x.weights[k].toFixed(2)})`).join(' · ')}; ช่วงราคาจากความผันผวน (Student-t)</p>
      <p className="mt-1 font-semibold text-slate-300">สมมติฐาน</p><ul className="list-disc pl-4">{x.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
      <p className="mt-1 text-slate-500">ล็อกไว้เมื่อ {new Date(x.made_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' })} น. · ราคา ณ {x.as_of_date} · sha {x.sha}</p>
    </div> : null })()}
    {c.drivers_th?.length > 0 && <p><span className="font-semibold text-slate-300">ปัจจัยหลักที่ควรติดตาม:</span> {c.drivers_th.join(' · ')}</p>}
    <p className="text-slate-500">ที่มาข้อมูล: {c.value_source}{c.change_from === 'proxy' ? ' · การเปลี่ยนแปลง/กราฟคำนวณจากตัวแทน' : ''}</p>
  </div>
}

function Row({ c }) {
  const [open, setOpen] = useState(false)
  const hz = Object.fromEntries((c.horizons || []).map(x => [x.horizon, x]))
  const up = (c.change_1m ?? 0) >= 0
  return <div className={`rounded-xl border p-3 ${c.holdings?.length ? 'border-amber-500/25 bg-amber-500/[0.03]' : 'border-[#2a2f3e] bg-[#121620]'}`}>
    <div className="grid items-center gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto_minmax(0,3.2fr)_auto]">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-white">{c.name_th}</p>
        <p className="truncate text-[10px] text-slate-500">{c.name_en}{c.proxy_th ? ` · proxy ${c.forecast_subject}` : ''}</p>
        {c.link_th && <span className="mt-1 inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-200">กระทบพอร์ต: {c.link_th}</span>}
      </div>
      <div>
        <p className="text-base font-bold text-white">{c.value === null || c.value === undefined ? <span className="text-amber-300">unknown</span> : fmt(c.value, c.is_rate)} <span className="text-[10px] font-normal text-slate-500">{c.unit}</span></p>
        {c.value2 && <p className="text-[10px] text-slate-400">{c.value2.label} {fmt(c.value2.value)}</p>}
        <p className="text-[10px] text-slate-500"><span className={(c.change_1d ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>{chg(c.change_1d, c.change_basis)}</span> วันล่าสุด · <span className={up ? 'text-emerald-400' : 'text-red-400'}>{chg(c.change_1m, c.change_basis)}</span> 1 เดือน{c.change_from === 'proxy' ? '*' : ''}</p>
        <p className="text-[10px] text-slate-600">ณ {thDate(c.as_of)}</p>
      </div>
      <Spark data={c.spark} up={up} />
      {c.info_only
        ? <p className="text-xs text-slate-300">{c.summary_th}</p>
        : <div className="grid grid-cols-5 gap-1.5">{['3d', '1m', '3m', '6m', '1y'].map(h => <HCell key={h} x={hz[h]} rate={c.is_rate} />)}</div>}
      <button onClick={() => setOpen(!open)} className="rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-400 hover:text-slate-200">{open ? 'ซ่อน' : 'วิธีคิด ▸'}</button>
    </div>
    {!c.info_only && <p className="mt-2 text-[11px] text-slate-400">💡 {c.summary_th}</p>}
    {open && <Detail c={c} />}
  </div>
}

function PolicyCard({ p }) {
  const [open, setOpen] = useState(false)
  return <div className="rounded-xl border border-[#2a2f3e] bg-[#121620] p-3">
    <div className="flex items-start justify-between gap-2">
      <div><p className="text-sm font-semibold text-white">{p.name_th}</p><p className="text-[10px] text-slate-500">{p.name_en}</p></div>
      {p.expected ? <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${PATH[p.expected]}`}>คาดครั้งหน้า: {p.expected_th}</span> : <span className="text-[11px] text-amber-300">unknown</span>}
    </div>
    <p className="mt-2 text-xl font-bold text-white">{p.status === 'ok' ? p.rate_text : <span className="text-amber-300">unknown</span>}</p>
    {p.status !== 'ok' && <p className="text-[10px] text-amber-300">ดึงข้อมูลไม่ได้: {p.error}</p>}
    <div className="mt-1 space-y-0.5 text-[11px] text-slate-400">
      {p.decision_date && <p>ประกาศล่าสุด: {thDate(p.decision_date)}{p.bank === 'FED' && p.last_meeting ? ` · ประชุมล่าสุด ${thDate(p.last_meeting)} (${p.last_meeting_outcome === 'hold' ? 'คงดอกเบี้ย' : 'เปลี่ยนแปลง'})` : ''}{p.decision_text ? ` · ${p.decision_text}` : ''}</p>}
      <p>เปลี่ยนแปลงครั้งล่าสุด: {p.last_change_date ? `${p.last_change_bp > 0 ? '+' : ''}${p.last_change_bp} bp (${thDate(p.last_change_date)})` : 'unknown'}</p>
      <p>ประชุมครั้งถัดไป: <span className="text-slate-200">{thDate(p.next_meeting)}</span>{p.next_meeting_note ? ' (วันที่ 20 ของเดือน)' : ''}</p>
      {p.lean_12m && <p>แนวโน้ม 12 เดือน: {({ hold: 'คงที่', cut: 'ลดลง', hike: 'สูงขึ้น' })[p.lean_12m]} · ความมั่นใจ{p.confidence_th}</p>}
      <p className="text-[10px] text-slate-500">{p.basis_th}</p>
      <p className="text-[10px] text-amber-200/80">กระทบพอร์ต: {p.link_th}</p>
      <p className="text-[10px] text-slate-500">{p.validation_th}</p>
    </div>
    <button onClick={() => setOpen(!open)} className="mt-2 rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{open ? 'ซ่อน' : 'เหตุผล ▸'}</button>
    {open && <div className="mt-2 rounded-lg bg-black/25 p-2 text-[11px] text-slate-400"><ul className="list-disc space-y-0.5 pl-4">{p.rationale_th.map((r, i) => <li key={i}>{r}</li>)}</ul>
      <p className="mt-1 text-[10px] text-slate-500">ที่มา: {p.source_url ? <a className="underline" href={p.source_url} target="_blank" rel="noreferrer">{p.source}</a> : p.source}</p></div>}
  </div>
}

export default function MacroTrendsBoard({ data, loading, error, retry }) {
  if (loading && !data) return <Skeleton className="h-[600px]" />
  if (error) return <Card><SectionTitle title="แนวโน้มตัวชี้วัดสำคัญ" /><ServiceError retry={retry} /></Card>
  const cards = data?.cards || []
  return <Card>
    <SectionTitle title="แนวโน้มตัวชี้วัดสำคัญ" subtitle="Macro Sentiment · พยากรณ์ 3 วัน / 1 เดือน / 3 เดือน / 6 เดือน / 1 ปี · ล็อกผลและตรวจกับราคาจริง" />
    <div className="mb-4 rounded-lg bg-[#121620] p-3 text-[11px] text-slate-400">
      <p>▲ ขึ้น / ▼ ลง / ◆ ทรงตัว พร้อมโอกาส P(ขึ้น) · ตัวเลขใต้ลูกศร = {data?.legend_th?.range} · ≈ = ประมาณจากตัวแทน (proxy) · ความมั่นใจ: {data?.legend_th?.confidence}</p>
      <p className="mt-1">ความแม่นยำ: {data?.legend_th?.validation} · การ์ดขอบสีส้ม = กระทบพอร์ตของคุณ</p>
      <p className="mt-1 text-amber-200/80">{data?.disclaimer_th}</p>
    </div>
    {(data?.groups || []).map(g => <Fragment key={g.key}>
      <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-200">{g.name_th}</h3>
      {g.key === 'rates' && <div className="mb-3 grid gap-3 md:grid-cols-3">{(data.policy || []).map(p => <PolicyCard key={p.key} p={p} />)}</div>}
      <div className="space-y-2">{cards.filter(c => c.group === g.key).map(c => <Row key={c.key} c={c} />)}</div>
    </Fragment>)}
    <p className="mt-4 text-[10px] text-slate-500">* = คำนวณจากตัวแทน · ข้อมูล: yfinance, กระทรวงการคลังสหรัฐฯ, NY Fed/Federal Reserve, ธปท., CFETS (chinamoney), BLS — ฟรีทั้งหมด · อัปเดต {data?.generated_at ? new Date(data.generated_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' }) + ' น.' : ''}</p>
  </Card>
}
