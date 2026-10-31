import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

// 2026-11-01: geopolitical / war-risk card. Context/display only - not used in signals, forecasts or rebalance.
// Scenario probabilities are JUDGMENT (config/geo_conflicts.json), market numbers are measured (yfinance, GPR index).
const LV = { high: ['สูง', 'bg-red-500/20 text-red-200'], elevated: ['สูงกว่าปกติ', 'bg-amber-500/20 text-amber-200'], normal: ['ปกติ', 'bg-emerald-500/20 text-emerald-200'] }
const pct = v => (v === null || v === undefined ? 'unknown' : `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`)
const MK = [['BZ=F', 'น้ำมันเบรนท์'], ['GC=F', 'ทองคำ'], ['^VIX', 'VIX (ความกลัว)'], ['THB=X', 'USD/THB']]

export default function GeoRiskCard({ data, loading, error, retry }) {
  if (loading && !data) return <Skeleton className="h-56" />
  if (error || !data) return <Card><SectionTitle title="ความเสี่ยงสงคราม/ภูมิรัฐศาสตร์" /><ServiceError retry={retry} compact /></Card>
  const a = data.assessment || {}, g = data.gpr?.daily || {}, ms = data.market_stress || {}
  const [lvTh, lvCls] = LV[data.level] || ['unknown', 'bg-slate-700 text-slate-200']
  const eu = (a.eu_preparedness_facts || [])[0]
  return <Card>
    <SectionTitle title="ความเสี่ยงสงคราม/ภูมิรัฐศาสตร์" subtitle={`ประเมิน ${a.assessed_at || 'unknown'}${a.assessment_stale ? ' · เก่าแล้ว (STALE)' : ''} · ใช้ประกอบเท่านั้น ไม่ใช้ใน signals`} />
    <div className="flex items-center gap-2 text-sm">
      <span className={`rounded px-2 py-0.5 font-semibold ${lvCls}`}>ระดับ: {lvTh}</span>
      <span className="text-[11px] text-slate-400">ดัชนี GPR เฉลี่ย 30 วัน {g.ma30 ?? 'unknown'} (สูงกว่า {g.ma30_pctile_since_1985 ?? '?'}% ของช่วงปี 1985-ปัจจุบัน) · ข้อมูลถึง {g.as_of || 'unknown'}</span>
    </div>
    <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{(a.conflicts || []).map(c => {
      const esc = (c.scenarios || []).filter(s => s.tier !== 'status_quo' && s.tier !== 'de_escalation').reduce((m, s) => m + (s.p || 0), 0)
      const n = data.news?.[c.key]
      return <div key={c.key} className="rounded-lg border border-[#2a2f3e] bg-[#121620] p-2.5">
        <div className="flex items-baseline justify-between gap-2"><span className="text-sm font-medium text-white">{c.name_th}</span>
          <span className={`text-xs font-semibold ${esc >= 0.25 ? 'text-red-300' : esc >= 0.1 ? 'text-amber-300' : 'text-slate-300'}`}>โอกาสลุกลาม ~{Math.round(esc * 100)}% <span className="font-normal text-slate-500">(ประเมิน)</span></span></div>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{c.status_th}</p>
        {n && <p className="mt-0.5 text-[10px] text-slate-500">ข่าว 7 วัน: {n.articles_7d} ชิ้น{n.volume_ratio ? ` (x${n.volume_ratio} จากปกติ)` : ''}</p>}
      </div> })}</div>
    {a.ww3 && <p className="mt-2 text-[12px] text-slate-300">🌍 {a.ww3.label_th}: <b>{a.ww3.p_12m}</b> ใน 12 เดือน <span className="text-slate-500">(ประเมิน ไม่ใช่ข้อมูลข่าวกรอง)</span></p>}
    <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] md:grid-cols-4">{MK.map(([k, l]) => { const m = ms[k]; return <div key={k} className="rounded bg-[#121620] px-2 py-1"><span className="text-slate-400">{l}</span> <span className="text-white">{m?.last == null ? 'unknown' : Number(m.last).toLocaleString('en-US', { maximumFractionDigits: 2 })}</span> <span className={m?.chg_1m_pct > 0 ? 'text-amber-300' : 'text-sky-300'}>{pct(m?.chg_1m_pct)} 1 เดือน</span></div> })}</div>
    {eu && <p className="mt-2 rounded bg-sky-900/20 p-2 text-[11px] leading-relaxed text-sky-100">ข่าว "ให้คนยุโรปตุนอาหาร": ที่จริงคือคำแนะนำให้มีของจำเป็นพอ <b>72 ชั่วโมง (3 วัน)</b> ของ EU (มี.ค. 2025) และแคมเปญ Be Ready ของอังกฤษ (22 ต.ค. 2026) เป็นการเตรียมพร้อมทุกภัย (น้ำท่วม ไซเบอร์ ไฟดับ สงคราม) ไม่ได้มาจากข่าวกรองว่าจะเกิดสงครามใหญ่</p>}
    <p className="mt-2 text-[10px] text-slate-500">พอร์ต: PTTEP มักได้ประโยชน์เมื่อน้ำมันขึ้น (ช่วงเริ่มสงครามอิหร่าน 27 ก.พ.-31 มี.ค. 2026: PTTEP {pct(data.holding_sensitivity?.['PTTEP.BK']?.iran_war_outbreak_move_pct)}, SCB {pct(data.holding_sensitivity?.['SCB.BK']?.iran_war_outbreak_move_pct)}, SCBGOLDE {pct(data.holding_sensitivity?.SCBGOLDE?.iran_war_outbreak_move_pct)} - เกิดครั้งเดียว ไม่ใช่การพยากรณ์) · ไม่มีคำแนะนำขาย PTTEP/SCB · ไอเดียป้องกันความเสี่ยงเป็นเพียงข้อเสนอ · ที่มา: GPR (Caldara-Iacoviello), Yahoo Finance, ข่าวในระบบ</p>
  </Card>
}
