import { X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { number } from '../utils/format'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'

const STOCK_LABELS = { dividend: 'ปันผล', growth: 'การเติบโต', value: 'มูลค่า', quality: 'คุณภาพ', technical: 'เทคนิค', xd_timing: 'จังหวะ XD' }
const FUND_LABELS = { income: 'ผลตอบแทนปันผล', total_return: 'ผลตอบแทนรวม 1 ปี', stability: 'ความนิ่ง', trend: 'แนวโน้ม', xd_timing: 'จังหวะ XD' }

const toneFor = (score) => (score >= 70 ? 'emerald' : score >= 55 ? 'blue' : 'gray')
const pct = (v) => (v === null || v === undefined ? '-' : `${number(v, 1)}%`)
const signed = (v) => (v === null || v === undefined ? '-' : `${v > 0 ? '+' : ''}${number(v, 2)}%`)

function ScoreBar({ value }) {
  const v = Number(value) || 0
  return <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-400" style={{ width: `${Math.min(100, Math.max(0, v))}%` }} /></div>
}

function XdLine({ xd }) {
  if (!xd?.next_xd?.date) return <span className="text-slate-500">XD ถัดไป: ไม่พบ</span>
  const alert = xd.next_xd.alert_within_60d
  return <span className={alert ? 'font-semibold text-amber-300' : 'text-slate-400'}>
    {alert ? `⚠ XD ใน ${xd.next_xd.days_to_xd} วัน` : `XD ถัดไป`} {xd.next_xd.date} {xd.next_xd.basis?.startsWith('estimated') ? '(ประมาณการ)' : '(ยืนยันแล้ว)'}
  </span>
}

function ItemButton({ item, labels, onClick }) {
  const overall = Number(item.scores?.overall) || 0
  return <button onClick={onClick} className="w-full rounded-xl border border-transparent bg-[#141925] p-3 text-left transition hover:border-emerald-500/30">
    <div className="flex items-center justify-between gap-2">
      <span className="rounded-lg bg-slate-700/60 px-2 py-1 text-xs font-bold text-white">{item.ticker}</span>
      <span className="truncate text-[10px] text-slate-400">{item.name}</span>
    </div>
    <div className="mt-2 flex items-baseline justify-between gap-2"><span className="text-base font-semibold text-white">{item.last != null ? number(item.last, 2) : '-'} <span className="text-[10px] font-normal text-slate-500">THB</span></span><span className="text-[10px] text-slate-500">ณ {item.last_date ?? '-'}</span></div>
    <div className="mt-2 flex items-center gap-3"><ScoreBar value={overall} /><span className="w-9 text-right text-xs font-semibold text-white">{number(overall, 0)}</span></div>
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-400">
      {Object.keys(labels).slice(0, 4).map(k => <span key={k}>{labels[k]} {item.scores?.[k] ?? '-'}</span>)}
    </div>
    <div className="mt-2 flex items-center justify-between gap-2 text-[10px]">
      <Badge tone={toneFor(overall)}>{item.rating}</Badge>
      <span className="text-slate-500">ปันผล {pct(item.yield_pct)}</span>
    </div>
    <div className="mt-2 text-[10px]"><XdLine xd={item.xd} /></div>
  </button>
}

function Detail({ item, labels, isFund, onClose }) {
  const xd = item.xd || {}
  const s = xd.summary || {}
  const rows = isFund
    ? [['ผลตอบแทนปันผล', pct(item.yield_pct)], ['1Y รวมปันผล', pct(item.r1y_total)], ['3Y รวมปันผล', pct(item.r3y_total)], ['ความผันผวน 1Y', pct(item.vol_1y)], ['ขาดทุนสูงสุด 3Y', pct(item.max_dd_3y)], ['ราคาล่าสุด', `${number(item.last, 2)} THB (${item.last_date ?? '-'})`]]
    : [['ราคาล่าสุด', `${number(item.last, 2)} THB (${item.last_date ?? '-'})`], ['ปันผล (yield)', pct(item.yield_pct)], ['P/E', number(item.trailingPE, 1)], ['P/B', number(item.pb, 2)], ['ROE', pct(item.roe)], ['กำไรโต', pct(item.eps_g)], ['RSI 14', number(item.rsi, 1)], ['จากจุดสูง 52 สัปดาห์', pct(item.dd52)]]
  const xdRows = [
    ['ปันผลเฉลี่ยต่อครั้ง (% ของราคาก่อน XD)', pct(s.avg_payout_pct)],
    ['ก่อน XD 5 วัน (เฉลี่ย)', signed(s.avg_pre5)],
    ['ก่อน XD 10 วัน (เฉลี่ย)', signed(s.avg_pre10)],
    ['หลัง XD 5 วัน (เฉลี่ย)', signed(s.avg_post5)],
    ['หลัง XD 10 วัน (เฉลี่ย)', signed(s.avg_post10)],
    ['ฟื้นตัวภายใน 20 วัน', s.recover20_pct == null ? '-' : `${number(s.recover20_pct, 0)}%`],
    ['จำนวนครั้ง XD ที่ใช้ (3 ปี)', s.events ?? '-'],
  ]
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
    <Card className="max-h-[90vh] w-full max-w-xl overflow-y-auto" onClick={event => event.stopPropagation()}>
      <div className="flex items-start justify-between"><div><p className="text-2xl font-bold text-white">{item.ticker}</p><p className="text-xs text-slate-400">{item.name}</p><div className="mt-2 flex items-center gap-2"><Badge tone={toneFor(item.scores.overall)}>{item.rating}</Badge><span className="text-sm font-semibold text-white">{number(item.scores.overall, 1)} / 100</span></div></div><button onClick={onClose} className="text-slate-500 hover:text-white"><X /></button></div>
      {xd.next_xd?.alert_within_60d && <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">⚠ {xd.next_xd.note}. ตรวจวัน XD ที่ตลาดหลักทรัพย์ก่อนตัดสินใจ</div>}
      <div className="mt-5 grid grid-cols-2 gap-3">{Object.entries(labels).map(([k, label]) => <div key={k} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] uppercase text-slate-500">{label}</p><p className="mt-1 text-sm font-medium text-white">{item.scores[k] ?? '-'}</p></div>)}</div>
      <div className="mt-4 grid grid-cols-2 gap-3">{rows.map(([k, v]) => <div key={k} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] uppercase text-slate-500">{k}</p><p className="mt-1 text-sm font-medium text-white">{v}</p></div>)}</div>
      {!isFund && <>
        <div className="mt-4 rounded-xl bg-[#121620] p-3"><p className="text-[10px] uppercase text-slate-500">วัน XD ถัดไป</p><p className="mt-1 text-sm text-white">{xd.next_xd?.date ? `${xd.next_xd.date} · ${xd.next_xd.basis}` : 'ไม่พบ'}</p><p className="mt-1 text-[10px] text-slate-500">ถ้าเป็นการประมาณการ มาจากวัน XD ปีก่อนบวก 365 วัน ยังไม่ได้ยืนยัน</p></div>
        <div className="mt-4"><p className="mb-2 text-xs font-semibold text-slate-300">ปันผลเทียบกับแนวโน้มราคาก่อน-หลัง XD (ข้อมูลย้อนหลัง 3 ปี, ไม่ได้ backtest)</p><div className="grid grid-cols-2 gap-3">{xdRows.map(([k, v]) => <div key={k} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] uppercase text-slate-500">{k}</p><p className="mt-1 text-sm font-medium text-white">{v}</p></div>)}</div>
          <p className="mt-3 rounded-xl bg-[#121620] p-3 text-xs text-slate-300">{xd.payout_vs_trend}</p>
          <p className="mt-2 rounded-xl bg-[#121620] p-3 text-xs text-slate-300">จังหวะเข้าซื้อ: {xd.timing_note}</p>
        </div></>}
      {item.held && <p className="mt-3 text-xs text-amber-300">หุ้นที่ถืออยู่ ไม่มีคำแนะนำขาย/ลด</p>}
      {item.flags?.length > 0 && <div className="mt-4"><p className="mb-1 text-xs font-semibold text-amber-300">ข้อควรระวัง</p><ul className="list-disc space-y-1 pl-5 text-xs text-slate-300">{item.flags.map(f => <li key={f}>{f}</li>)}</ul></div>}
      <div className="mt-4"><p className="mb-1 text-xs font-semibold text-slate-300">ข่าวและมุมมอง (มีวันที่ตามแหล่งที่พบ)</p><ul className="list-disc space-y-1 pl-5 text-xs text-slate-400">{item.news?.map(n => <li key={n}>{n}</li>)}</ul></div>
      <p className="mt-5 text-[10px] text-slate-500">ราคาล่าสุด ณ {item.last_date} · ยังไม่ผ่าน backtest · ใช้ประกอบการดูเท่านั้น ไม่มีการส่งคำสั่งซื้อขาย</p>
    </Card>
  </div>
}

export default function OpportunityPanel({ watchlist, loading, error, retry }) {
  const [tab, setTab] = useState('stocks')
  const [selected, setSelected] = useState(null)
  const stocks = useMemo(() => [...(watchlist?.stocks || [])].sort((a, b) => b.scores.overall - a.scores.overall), [watchlist])
  const funds = useMemo(() => [...(watchlist?.funds || [])].sort((a, b) => b.scores.overall - a.scores.overall), [watchlist])
  if (loading) return <Skeleton className="h-96" />
  const isFund = tab === 'funds'
  const list = isFund ? funds : stocks
  const labels = isFund ? FUND_LABELS : STOCK_LABELS
  return <><Card className="h-full">
    <SectionTitle title="Watch list ไทย" subtitle={`หุ้นไทย ${stocks.length} ตัว · กองทุนไทย ${funds.length} กอง · ยังไม่ผ่าน backtest`} />
    <div className="mb-3 flex gap-2">{[['stocks', `หุ้น (${stocks.length})`], ['funds', `กองทุน (${funds.length})`]].map(([key, label]) => <button key={key} onClick={() => setTab(key)} className={`rounded-lg px-3 py-1 text-xs font-semibold ${tab === key ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700/40 text-slate-400 hover:text-white'}`}>{label}</button>)}</div>
    {error ? <ServiceError retry={retry} compact /> : !watchlist ? <p className="py-16 text-center text-sm text-slate-500">ยังไม่มีข้อมูล watch list</p> :
    <div className="max-h-[70vh] space-y-2 overflow-y-auto pr-1">{list.map(item => <ItemButton key={item.ticker} item={item} labels={labels} onClick={() => setSelected(item)} />)}</div>}
    {watchlist && <p className="mt-3 text-[10px] text-slate-500">ราคาล่าสุด {watchlist.as_of_prices} · {watchlist.price_source}</p>}
  </Card>
  {selected && <Detail item={selected} labels={labels} isFund={isFund} onClose={() => setSelected(null)} />}
  </>
}
