import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { number } from '../utils/format'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-10-31: time-weighted (flow-neutral) daily series from /portfolio/performance.series.
// No synthetic Start/Now line: if the API has no series we show the reason instead of drawing one.
const fmtDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' })
const pctText = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${number(v, 2)}%`)

export default function PerformanceChart({ data, loading, error, retry, days, setDays }) {
  if (loading) return <Skeleton className="h-[420px]" />
  const series = data?.series || []
  const bm = data?.benchmark_comparison || {}
  const w = data?.window || {}
  const stats = [
    ['Return (TWR)', pctText(data?.total_return_pct), w.start ? `${fmtDate(w.start)} – ${fmtDate(w.end)}` : null],
    ['Sharpe', data?.sharpe_ratio == null ? '—' : number(data.sharpe_ratio, 2), data?.sharpe_ratio == null ? data?.sharpe_note : `rf ${data?.risk_free?.annual_pct ?? 0}% · vol ${number(data?.vol_pct, 1)}%`],
    ['Max drawdown', data?.max_drawdown == null ? '—' : `${number(data.max_drawdown, 2)}%`, data?.mdd_note],
    ['SET (TDEX proxy)', pctText(bm.SET?.return), bm.SET?.return != null && data?.total_return_pct != null ? `ส่วนต่าง ${pctText(bm.SET.alpha)}` : bm.SET?.error],
    ['S&P 500 (USD)', pctText(bm.SP500?.return), bm.SP500?.return != null && data?.total_return_pct != null ? `ส่วนต่าง ${pctText(bm.SP500.alpha)}` : bm.SP500?.error],
  ]
  return <Card><SectionTitle title="ผลตอบแทนพอร์ต" subtitle="Time-weighted return vs benchmarks · เงินซื้อเพิ่ม/ถอน ไม่นับเป็นกำไร" action={<div className="flex rounded-lg bg-[#121620] p-1">{[7, 30, 90].map(value => <button key={value} onClick={() => setDays(value)} className={`rounded-md px-3 py-1.5 text-xs ${days === value ? 'bg-blue-500 text-white' : 'text-slate-500'}`}>{value}D</button>)}</div>} />
    {error ? <ServiceError retry={retry} /> : <>
      {data?.provisional_note_th && <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">⚠️ {data.provisional_note_th}</div>}
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-5">{stats.map(([key, value, sub]) => <div key={key} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] text-slate-500">{key}</p><p className="mt-1 text-sm font-semibold text-white">{value}</p>{sub && <p className="mt-0.5 text-[10px] leading-tight text-slate-500">{sub}</p>}</div>)}</div>
      {series.length < 2 ? <p className="py-16 text-center text-sm text-slate-500">ยังไม่มีข้อมูลรายวันพอสำหรับกราฟในช่วงนี้{data?.error ? ` (${data.error})` : ''}</p> :
      <div className="h-72"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={series}><defs><linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10b981" stopOpacity={0.25} /><stop offset="100%" stopColor="#10b981" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="#2a2f3e" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis tickFormatter={value => `${number(value, 1)}%`} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} domain={['auto', 'auto']} width={48} />
        <Tooltip contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} labelFormatter={(d, p) => `${fmtDate(d)} ${d.slice(0, 4)}${p?.[0]?.payload?.reconstructed ? ' · reconstructed' : ''}`} formatter={(value, name) => [pctText(value), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="portfolio" name="พอร์ต (TWR)" stroke="#10b981" fill="url(#portfolioFill)" isAnimationActive={false} strokeWidth={2} dot={series.length <= 31 ? { r: 2 } : false} />
        <Line type="monotone" dataKey="SET" name="SET (TDEX)" stroke="#3b82f6" dot={false} isAnimationActive={false} strokeWidth={2} connectNulls />
        <Line type="monotone" dataKey="SP500" name="S&P 500 (USD)" stroke="#a78bfa" dot={false} isAnimationActive={false} strokeWidth={2} connectNulls />
      </ComposedChart></ResponsiveContainer></div>}
      <div className="mt-3 space-y-1 text-[10px] text-slate-500">
        {(data?.notes || []).map(n => <p key={n}>• {n}</p>)}
        <p>• วิธีคำนวณ: ผลตอบแทนถ่วงเวลา (TWR) จากจำนวนหน่วยใน snapshot × ราคาปิด/NAV รายวัน · ทุกเส้นเริ่มที่ 0% วันเดียวกัน · SET ใช้ TDEX.BK (SET50 ETF) แทนดัชนี SET ซึ่งไม่มีข้อมูลฟรี · S&P 500 เป็นสกุล USD</p>
      </div>
    </>}
  </Card>
}
