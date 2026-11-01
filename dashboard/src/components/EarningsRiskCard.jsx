import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-11-01 (Tho t39u, INTC -28.6% on 30 Oct): earnings-event gap risk. DISPLAY ONLY - not in signal scores or weights.
// Forecast bands already widen live when earnings fall inside the 3d/1m horizon (gate PASS); post-gap block = shadow.
const LV = { imminent: ['ใกล้มาก ≤5 วันทำการ', 'bg-red-500/20 text-red-200'], soon: ['เร็วๆ นี้ ≤15 วันทำการ', 'bg-amber-500/20 text-amber-200'], none: ['', ''] }
const ROLE = { holding: 'ถืออยู่', watch: 'watch list', bellwether: 'ตัวนำกลุ่ม (ไม่ได้อยู่ใน watch list)' }
const pct = v => (v === null || v === undefined ? 'unknown' : `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`)
const ict = s => (s ? s.slice(0, 16).replace('T', ' ') + ' ICT' : 'unknown')

export default function EarningsRiskCard({ data, loading, error, retry }) {
  if (loading && !data) return <Skeleton className="h-48" />
  if (error || !data) return <Card><SectionTitle title="ความเสี่ยงช่วงประกาศงบ (earnings gap)" /><ServiceError retry={retry} compact /></Card>
  const items = data.items || []
  const show = items.filter(i => i.role !== 'bellwether' || i.level !== 'none' || i.post_gap_watch)
  const p = data.post_gap_stats || {}
  return <Card>
    <SectionTitle title="ความเสี่ยงช่วงประกาศงบ (earnings gap)" subtitle={`อัปเดต ${ict(data.generated_at)} · แสดงผลเท่านั้น ไม่ใช้ในคะแนน signal · บทเรียนจาก INTC -28.6% (30 ต.ค.)`} />
    <div className="overflow-x-auto"><table className="w-full text-[11px]">
      <thead className="text-slate-400"><tr><th className="text-left">หุ้น</th><th className="text-left">ประกาศงบครั้งถัดไป</th><th>อีก (วันทำการ)</th><th>ขยับวันงบ (มัธยฐาน / p90 / แย่สุด)</th><th className="text-left">หมายเหตุ</th></tr></thead>
      <tbody>{show.map(i => {
        const [lv, cls] = LV[i.level] || LV.none
        return <tr key={i.ticker} className="border-t border-[#2a2f3e]">
          <td className="py-1 text-white">{i.ticker}<div className="text-[10px] text-slate-500">{ROLE[i.role]}</div></td>
          <td>{ict(i.next_earnings_ict)}<div className="text-[10px] text-slate-500">{i.timing || ''}</div></td>
          <td className="text-center">{i.trading_days_to ?? 'unknown'}{lv && <div><span className={`rounded px-1 ${cls}`}>{lv}</span></div>}</td>
          <td className="text-center">{i.median_abs_move_pct == null ? 'unknown' : `±${i.median_abs_move_pct}% / ±${i.p90_abs_move_pct}% / ${pct(i.worst_move_pct)}`}<div className="text-[10px] text-slate-500">{i.hist_n} ครั้งล่าสุด</div></td>
          <td className="text-slate-300">
            {i.post_gap_watch && i.last_reaction && <div className="text-amber-200">หลังงบร่วง {pct(i.last_reaction.move_pct)} ({i.last_reaction.reaction_day}) · รอฐานราคาก่อนเข้า swing</div>}
            {i.read_through && <div className="text-slate-400">กระทบต่อ: {i.read_through.join(', ')}</div>}
            {i.level !== 'none' && <div className="text-red-200">ราคาอาจกระโดดข้าม stop ได้ · กำหนดขนาดตามช่องว่างราคา หรือรอหลังประกาศงบ</div>}
          </td>
        </tr> })}</tbody></table></div>
    <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
      กรอบพยากรณ์ราคา (3 วัน / 1 เดือน) ขยายอัตโนมัติ ×{data.band_rule?.mult?.['3d'] ?? '?'} / ×{data.band_rule?.mult?.['1m'] ?? '?'} เมื่อมีวันประกาศงบอยู่ในช่วงพยากรณ์ (ผ่าน walk-forward gate) ·
      หลังงบร่วง ≥7% ในกลุ่มนี้ (5 ปี, n={p.n ?? '?'}) 20 วันถัดไปมัธยฐาน {pct(p.median_next20d_pct)} — ไม่มีแนวโน้มไหลต่อที่เชื่อถือได้ (กฎ "ห้ามเข้าหลังงบร่วง" อยู่ในโหมด shadow) ·
      หุ้นไทยที่ถืออยู่ติดตามวันงบใน morning brief · ไม่มีคำแนะนำขาย PTTEP/SCB · ที่มา: Yahoo Finance (วันงบที่บริษัทประกาศ + ราคาปิด)</p>
  </Card>
}
