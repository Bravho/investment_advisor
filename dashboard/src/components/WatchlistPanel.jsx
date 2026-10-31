import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { useState } from 'react'
import { number } from '../utils/format'
import { useFundWatchlist } from '../hooks/useNews'

const statusTone = { ready: 'green', watching: 'blue', dropped: 'gray' }
const ago = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'Asia/Bangkok' })
}
const zone = (lo, hi) => (lo == null && hi == null ? <span className="text-slate-600">not set</span> : `${lo ?? '-'} – ${hi ?? '-'}`)

const pct = (v, d = 1) => v == null ? <span className="text-slate-600">—</span> : <span className={v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'}>{v > 0 ? '+' : ''}{number(v, d)}%</span>
const TAX_TYPES = ['ThaiESG', 'ThaiESGX', 'RMF', 'SSF']

function FundTable({ items, rules }) {
  if (!items.length) return <p className="py-8 text-center text-sm text-slate-500">ไม่มีกองทุนในกลุ่มนี้</p>
  return <div className="max-h-[560px] overflow-auto">
    <table className="w-full text-left text-xs">
      <thead className="sticky top-0 bg-[#1a1f2e] text-[10px] uppercase text-slate-500">
        <tr><th className="py-2 pr-2">กองทุน</th><th className="pr-2 text-right">NAV</th><th className="pr-2 text-right">1m</th><th className="pr-2 text-right">YTD</th><th className="pr-2 text-right">1y</th><th className="pr-2 text-right">3y/yr</th><th className="pr-2 text-right">TER</th><th className="pr-2 text-center">Risk</th><th className="pr-2">FX</th><th className="pr-2 text-right">RSI</th><th className="pr-2">Entry</th><th className="text-right">Score</th></tr>
      </thead>
      <tbody>{items.map(f => {
        const r = f.returns || {}, fee = f.fees || {}, b = f.score_basis || {}
        const scoreTip = f.score == null ? (b.missing_th || 'ไม่มีคะแนน') :
          `${b.definition_th}\nต้นทุน ${b.cost}% (${b.cost_basis}) → ${b.cost_pts} คะแนน\nผลตอบแทน/ความผันผวน ${b.horizon}: ${b.ret_per_vol} vs กลุ่ม ${b.peer_ret_per_vol} → ${b.riskadj_pts} คะแนน`
        return <tr key={f.code} className="border-t border-slate-800/80 align-top">
          <td className="py-2 pr-2 max-w-[340px]">
            <div className="flex flex-wrap items-center gap-1"><a href={f.source_url} target="_blank" rel="noreferrer" className="font-semibold text-white hover:underline">{f.code}</a>
              {f.tax_type && <Badge tone="blue">{f.tax_type}</Badge>}{f.status === 'holding' && <Badge tone="green">HOLDING</Badge>}</div>
            <div className="text-[10px] text-slate-500">{f.amc || 'unknown'} · {f.aimc_category || 'unknown'}</div>
            <div className="text-[11px] text-slate-300">{f.reason_th}</div>
            {f.tax_type && <div className="text-[10px] text-sky-300/80" title={rules?.[f.tax_type]}>🧾 {(rules?.[f.tax_type] || '').split(' · ')[0]}</div>}
            {fee.note_th && <div className="text-[10px] text-amber-300/80">{fee.note_th}</div>}
            {f.error && <div className="text-[10px] text-red-400">ข้อมูลไม่ครบ: {f.error}</div>}
          </td>
          <td className="pr-2 text-right"><div className="text-white">{f.nav == null ? 'unknown' : number(f.nav, 4)}</div><div className={`text-[10px] ${f.nav_stale ? 'text-amber-400' : 'text-slate-500'}`}>{f.nav_stale ? 'STALE · ' : ''}{ago(f.nav_date)}</div></td>
          <td className="pr-2 text-right">{pct(r['1m'])}</td><td className="pr-2 text-right">{pct(r.ytd)}</td><td className="pr-2 text-right">{pct(r['1y'])}</td><td className="pr-2 text-right">{pct(r['3y'])}</td>
          <td className="pr-2 text-right text-slate-300" title={`ค่าจัดการเก็บจริง ${fee.mgmt_actual ?? 'unknown'}% · เพดานค่าจัดการ ${fee.mgmt_max ?? fee.mgmt_ceiling_detail ?? 'unknown'}% · front ${fee.front_actual ?? '?'}% · back ${fee.back_actual ?? '?'}%`}>{fee.ter_actual == null ? <span className="text-slate-600">unknown</span> : `${number(fee.ter_actual, 2)}%`}<div className="text-[10px] text-slate-500">จัดการ {fee.mgmt_actual ?? '?'}%</div></td>
          <td className="pr-2 text-center text-slate-300">{f.risk_level ?? '—'}</td>
          <td className="pr-2 text-[10px] text-slate-400 max-w-[120px]">{f.is_foreign ? (f.fx_hedge || 'unknown') : 'สินทรัพย์ไทย'}</td>
          <td className="pr-2 text-right text-slate-600" title="กองทุนไม่มีราคาระหว่างวัน — ไม่ใช้ RSI">—</td><td className="pr-2 text-slate-600">—</td>
          <td className="text-right text-slate-200 cursor-help" title={scoreTip}>{f.score == null ? <span className="text-slate-600">—</span> : number(f.score, 0)}</td>
        </tr>
      })}</tbody>
    </table>
  </div>
}

export default function WatchlistPanel({ payload, loading, error, retry }) {
  const [tab, setTab] = useState(() => { const q = new URLSearchParams(window.location.search).get('wl'); return ['tax', 'general'].includes(q) ? q : 'stocks' })
  const [taxType, setTaxType] = useState('all')
  const funds = useFundWatchlist()
  if (loading) return <Skeleton className="h-96" />
  const items = payload?.items || []
  const fp = funds.data || {}
  const fItems = fp.items || []
  const counts = fp.counts || {}
  const tabs = [['stocks', 'หุ้น/ETF', items.length], ['tax', 'กองทุนลดหย่อนภาษี', counts.tax ?? 0], ['general', 'กองทุนทั่วไป', counts.general ?? 0]]
  const tabBar = <div className="mb-3 flex flex-wrap gap-2">{tabs.map(([k, label, n]) =>
    <button key={k} onClick={() => setTab(k)} className={`rounded-lg px-3 py-1.5 text-xs ${tab === k ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>{label} <span className="opacity-70">({n})</span></button>)}</div>
  if (tab !== 'stocks') {
    const shown = fItems.filter(f => f.group_key === tab && (tab !== 'tax' || taxType === 'all' || f.tax_type === taxType))
    return <Card>
      <SectionTitle title="รายการเฝ้าดูการลงทุน" subtitle={`${tab === 'tax' ? 'กองทุนลดหย่อนภาษี' : 'กองทุนทั่วไป (ไม่มีสิทธิลดหย่อน)'} · NAV จาก ${fp.source || 'Finnomena'} · NAV เก่ากว่า ${fp.stale_after_days ?? 7} วัน = STALE`} />
      {tabBar}
      {tab === 'tax' && <div className="mb-3 flex flex-wrap gap-1.5">{['all', ...TAX_TYPES].map(t =>
        <button key={t} onClick={() => setTaxType(t)} className={`rounded-full px-2.5 py-0.5 text-[11px] ${taxType === t ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-400'}`}>{t === 'all' ? 'ทั้งหมด' : t} ({t === 'all' ? counts.tax ?? 0 : counts.by_tax_type?.[t] ?? 0})</button>)}</div>}
      {tab === 'tax' && taxType === 'SSF' && <p className="mb-2 text-[11px] text-amber-300/80">{fp.tax_rules_th?.SSF}</p>}
      {funds.loading ? <Skeleton className="h-72" /> : funds.error ? <ServiceError retry={funds.refetch} compact /> : <FundTable items={shown} rules={fp.tax_rules_th} />}
      <p className="mt-3 text-[10px] text-slate-500">{fp.score_definition_th} · RSI/โซนเข้าซื้อ "—" เพราะกองทุนซื้อขายที่ NAV สิ้นวัน · {fp.note_th} · ค่าธรรมเนียมจาก Finnomena อาจต่างจาก factsheet</p>
    </Card>
  }
  return <Card>
    <SectionTitle title="รายการเฝ้าดูการลงทุน" subtitle={`Investment watch list · ${items.length} ideas · prices stale after ${payload?.stale_after_days ?? 7} days`} />
    {tabBar}
    {error ? <ServiceError retry={retry} compact /> : !items.length ? <p className="py-10 text-center text-sm text-slate-500">No watch-list items</p> :
    <div className="max-h-[520px] overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-[#1a1f2e] text-[10px] uppercase text-slate-500">
          <tr><th className="py-2 pr-2">Ticker</th><th className="pr-2">Status</th><th className="pr-2 text-right">Price</th><th className="pr-2 text-right">1d</th><th className="pr-2 text-right">RSI</th><th className="pr-2">Entry zone</th><th className="pr-2">Target</th><th className="pr-2 text-right">Score</th><th>Alerts</th></tr>
        </thead>
        <tbody>{items.map(item => {
          const m = item.metrics || {}
          const chg = m.change_1d_pct
          return <tr key={item.ticker} className="border-t border-slate-800/80 align-top" title={item.thesis || ''}>
            <td className="py-2 pr-2"><div className="font-semibold text-white">{item.ticker}</div><div className="text-[10px] text-slate-500">{item.name} · {item.sector}</div></td>
            <td className="pr-2"><Badge tone={statusTone[item.status]}>{item.status}</Badge></td>
            <td className="pr-2 text-right"><div className="text-white">{number(item.last_price, 2)} <span className="text-[10px] text-slate-500">{item.currency}</span></div><div className={`text-[10px] ${item.price_stale ? 'text-amber-400' : 'text-slate-500'}`}>{item.price_stale ? 'STALE · ' : ''}{ago(item.price_as_of)} · {item.price_source || 'n/a'}</div></td>
            <td className={`pr-2 text-right ${chg > 0 ? 'text-emerald-400' : chg < 0 ? 'text-red-400' : 'text-slate-400'}`}>{chg == null ? '-' : `${chg > 0 ? '+' : ''}${number(chg, 2)}%`}</td>
            <td className="pr-2 text-right text-slate-300">{m.rsi14 == null ? '-' : number(m.rsi14, 0)}</td>
            <td className="pr-2 text-slate-300">{zone(item.entry_low, item.entry_high)}</td>
            <td className="pr-2 text-slate-300">{item.target_price ?? <span className="text-slate-600">-</span>}</td>
            <td className="pr-2 text-right text-slate-300">{item.score == null ? '-' : number(item.score, 0)}</td>
            <td className="text-[10px] text-amber-300">{(item.active_conditions || []).map(c => <div key={c}>🔔 {c.replace(`${item.ticker} `, '')}</div>)}</td>
          </tr>
        })}</tbody>
      </table>
      <p className="mt-3 text-[10px] text-slate-500">{payload?.note} Hover a row for its thesis. Costs/fees/tax per idea: GET /api/portfolio/watchlist.</p>
    </div>}
  </Card>
}
