import { useState } from 'react'
import { portfolioClient } from '../config/api'
import { Badge, Card, SectionTitle, ServiceError, Skeleton, SourceBadge } from './UI'
import { number } from '../utils/format'

const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')

// Trade plans with approve / reject -> PATCH /trade-plans/{id} through the same-origin proxy (behind the auth proxy when remote).
export default function DeskPlans({ plans, journal, loading, error, retry, approved, audit, onChanged }) {
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)
  if (loading) return <Skeleton className="h-64" />
  if (error || !plans) return <Card><SectionTitle title="Trade plans" /><ServiceError retry={retry} compact /></Card>
  const rows = [...(plans.plans || [])].sort((a, b) => (b.checklist_pass - a.checklist_pass) || (b.viable - a.viable) || ((b.rr || 0) - (a.rr || 0)))
  const send = (p, body) => portfolioClient.patch(`/trade-plans/${p.id}`, body)
  const act = async (p, status) => {
    const note = status === 'rejected' ? window.prompt(`ปฏิเสธแผน #${p.id} ${p.ticker}? เหตุผล (ไม่บังคับ):`, '') : (window.confirm(`อนุมัติแผน #${p.id} ${p.ticker}? ระบบจะคัดลอกโซนเข้า ${fmt(p.entry_low)}–${fmt(p.entry_high)}, stop ${fmt(p.stop)}, เป้า ${fmt(p.target)} ไปที่ watch list (แจ้งเตือนเท่านั้น ไม่มีการส่งคำสั่งซื้อขาย)`) ? '' : null)
    if (note === null) return
    setBusy(p.id); setMsg(null)
    const stamp = new Date().toLocaleString('en-GB', { timeZone: 'Asia/Bangkok' })
    const body = { status, review_note: `${status} on trading desk ${stamp} ICT${note ? ': ' + note : ''}` }
    try {
      await send(p, body)
      setMsg({ ok: true, text: `#${p.id} ${p.ticker} → ${status === 'approved' ? 'อนุมัติแล้ว' : 'ปฏิเสธแล้ว'}` }); retry(); onChanged?.()
    } catch (e) {
      const detail = String(e?.response?.data?.detail || e.message || '')
      // 2026-11-01 (Tho t27u): engine refuses (400) plans that fail viability / freshness / checklist.
      // Explain in Thai and let Tho type an override reason; the plan is then shown as "อนุมัติแบบ override".
      if (status === 'approved' && e?.response?.status === 400 && /override_reason/.test(detail)) {
        const why = detail.replace(/^bad plan: /, '').replace(/; provide a non-empty override_reason to override$/, '')
        const reason = window.prompt(`ระบบไม่อนุมัติแผน #${p.id} ${p.ticker} อัตโนมัติ เพราะ: ${why}\n\nถ้ายังต้องการอนุมัติ ให้พิมพ์เหตุผล (จะแสดงป้าย "อนุมัติแบบ override" พร้อมเหตุผลนี้ทุกที่ที่แผนนี้ปรากฏ):`, '')
        if (reason && reason.trim()) {
          try {
            await send(p, { ...body, override_reason: reason.trim() })
            setMsg({ ok: true, text: `#${p.id} ${p.ticker} → อนุมัติแบบ override: ${reason.trim()}` }); retry(); onChanged?.()
          } catch (e2) { setMsg({ ok: false, text: `#${p.id} อนุมัติไม่สำเร็จ: ${e2?.response?.data?.detail || e2.message}` }) }
        } else setMsg({ ok: false, text: `#${p.id} ${p.ticker} ยังไม่ถูกอนุมัติ: ${why} (ไม่ได้ใส่เหตุผล override)` })
      } else setMsg({ ok: false, text: `#${p.id} ทำรายการไม่สำเร็จ (${e?.response?.status || 'network'}): ${detail}` })
    }
    setBusy(null)
  }
  const newest = rows.reduce((m, p) => (p.updated_at > m ? p.updated_at : m), '')
  const j = journal?.items || []
  return <Card>
    <SectionTitle title="Trade plans" subtitle="Engine PROPOSED · approve/reject = PATCH /trade-plans/{id}" action={<div className="flex gap-1"><Badge tone="yellow">{rows.length} proposed</Badge><SourceBadge source="engine · yfinance" asOf={newest} /></div>} />
    {msg && <p className={`mb-1 rounded px-2 py-1 text-[11px] ${msg.ok ? 'bg-sky-900/30 text-sky-200' : 'bg-red-900/30 text-red-200'}`}>{msg.text}</p>}
    <div className="max-h-[420px] overflow-auto"><table className="w-full text-[11px]">
      <thead className="sticky top-0 bg-[#151a24] text-[10px] uppercase text-slate-500"><tr><th className="text-left">#</th><th className="text-left">Ticker</th><th className="text-right">Last</th><th className="text-right">Entry</th><th className="text-right">Stop</th><th className="text-right">Target</th><th className="text-right">R:R</th><th className="text-right">Size</th><th>Chk</th><th>Price as of</th><th></th></tr></thead>
      <tbody>{rows.map(p => { const pa = p.inputs?.last_price?.as_of || p.inputs?.atr14?.as_of; return <tr key={p.id} className={`border-t border-slate-800/80 ${p.viable ? '' : 'text-slate-500'}`} title={p.rationale}>
        <td className="py-0.5 text-slate-500">{p.id}</td><td className="text-slate-200">{p.ticker}{p.setup && <span title={p.setup} className="ml-1 rounded bg-violet-900/60 px-1 text-[9px] text-violet-200">{p.setup === 'momentum_base_swing' ? 'MB swing' : p.setup}</span>}</td><td className="text-right">{fmt(p.last_price)}</td><td className="text-right">{fmt(p.entry_low)}–{fmt(p.entry_high)}</td>
        <td className="text-right text-red-300">{fmt(p.stop)}</td><td className="text-right text-emerald-300">{fmt(p.target)}</td><td className="text-right">{number(p.rr, 1)}</td>
        <td className="text-right">{p.size?.shares ?? '-'}</td><td className="text-center">{p.checklist_pass ? <Badge tone="green">pass</Badge> : <Badge tone="red">fail</Badge>}</td>
        <td className="text-center"><SourceBadge asOf={pa} staleHours={96} /></td>
        <td className="whitespace-nowrap text-right"><button disabled={busy === p.id} onClick={() => act(p, 'approved')} className="mr-1 rounded bg-emerald-700/70 px-2 py-0.5 text-[10px] text-white hover:bg-emerald-600 disabled:opacity-40">Approve</button>
          <button disabled={busy === p.id} onClick={() => act(p, 'rejected')} className="rounded bg-red-800/70 px-2 py-0.5 text-[10px] text-white hover:bg-red-700 disabled:opacity-40">Reject</button></td>
      </tr> })}</tbody></table></div>
    <div className="mt-3"><p className="mb-1 text-xs font-semibold text-slate-300">แผนที่อนุมัติแล้ว (แจ้งเตือนเท่านั้น)</p>
      {!(approved?.plans || []).length ? <p className="text-[11px] text-slate-500">ยังไม่มีแผนที่อนุมัติ</p> :
        <table className="w-full text-[11px]"><tbody>{approved.plans.map(p => <tr key={p.id} className="border-t border-slate-800/80">
          <td className="py-0.5 text-slate-500">{p.id}</td><td className="text-slate-200">{p.ticker}</td><td className="text-right">{fmt(p.entry_low)}–{fmt(p.entry_high)}</td><td className="text-right text-red-300">{fmt(p.stop)}</td><td className="text-right text-emerald-300">{fmt(p.target)}</td>
          <td>{p.approved_by_override ? <span title={p.override_reason} className="rounded bg-orange-600/30 px-1.5 py-0.5 text-[10px] font-semibold text-orange-200">⚠ {p.override_badge_th}</span> : <Badge tone="green">อนุมัติปกติ</Badge>}</td></tr>)}</tbody></table>}
    </div>
    <div className="mt-3"><p className="mb-1 text-xs font-semibold text-slate-300">ประวัติการอนุมัติ</p>
      {!(audit?.items || []).length ? <p className="text-[11px] text-slate-500">ยังไม่มีประวัติ</p> :
        <table className="w-full text-[11px]"><tbody>{audit.items.map(a => <tr key={a.id} className="border-t border-slate-800/80">
          <td className="py-0.5 text-slate-500">{new Date(a.created_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td><td>#{a.plan_id} {a.ticker}</td><td>{a.action}</td>
          <td>{a.by_override ? <span className="rounded bg-orange-600/30 px-1.5 py-0.5 text-[10px] font-semibold text-orange-200">⚠ {a.badge_th}</span> : <span className="text-slate-500">{a.note || ''}</span>}</td></tr>)}</tbody></table>}
    </div>
    <div className="mt-3"><p className="mb-1 text-xs font-semibold text-slate-300">Journal <SourceBadge source="trade_journal" asOf={j[0]?.updated_at || j[0]?.created_at} staleHours={24 * 30} /></p>
      {j.length === 0 ? <p className="text-[11px] text-slate-500">No journal entries yet (POST /journal; PATCH /journal/&#123;id&#125; on exit).</p> :
        <table className="w-full text-[11px]"><tbody>{j.map(e => <tr key={e.id} className="border-t border-slate-800/80"><td>{e.ticker}</td><td>{e.opened_at}</td><td>{e.closed_at || 'open'}</td><td className="text-right">{number(e.pnl, 0)}</td><td className="text-right">{number(e.r_multiple, 2)}R</td><td>{e.grade || '-'}</td><td className="text-slate-400">{e.lessons || ''}</td></tr>)}</tbody></table>}
    </div>
  </Card>
}
