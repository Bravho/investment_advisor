// 2026-11-01: plain-Thai contagion read-out for one event (crypto or geo). Display only - not a trading signal.
const TONE = { contagion: 'border-red-500/40 bg-red-900/25 text-red-100', watch: 'border-amber-500/40 bg-amber-900/20 text-amber-100',
  contained: 'border-emerald-500/30 bg-emerald-900/15 text-emerald-100', pending: 'border-slate-600 bg-slate-800/40 text-slate-200' }
const p = v => (v === null || v === undefined ? 'unknown' : `${v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`)

export default function ContagionBlock({ ev, rule }) {
  if (!ev) return null
  const m = ev.moves || {}
  const rows = [['BTC', p(m['BTC-USD']?.chg_pct)], ['S&P 500 (SPY)', p(m.SPY?.chg_pct)], ['Nasdaq (QQQ)', p(m.QQQ?.chg_pct)],
    ['VIX', m['^VIX']?.last == null ? 'unknown' : `${m['^VIX'].last} (${m['^VIX'].chg_abs > 0 ? '+' : ''}${m['^VIX'].chg_abs} จุด)`],
    ['COIN', p(m.COIN?.chg_pct)], ['MSTR', p(m.MSTR?.chg_pct)], ['ทองคำ', p(m['GC=F']?.chg_pct)], ['USD/THB', p(m['THB=X']?.chg_pct)]]
  return <div className={`mt-2 rounded-lg border p-2.5 text-[11px] ${TONE[ev.level] || TONE.pending}`}>
    <p className="text-xs font-semibold">ลามสู่ตลาดหุ้นหรือไม่: {ev.level_th}</p>
    <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 md:grid-cols-4">{rows.map(([k, v]) => <span key={k}><span className="opacity-70">{k}</span> {v}</span>)}</div>
    <p className="mt-1 opacity-70">วัดจากราคาปิด {m.SPY?.anchor_date || '?'} (ก่อนเกิดเหตุ) ถึง {m.SPY?.last_date || '?'} · BTC ถึง {m['BTC-USD']?.last_date || '?'} · Yahoo Finance</p>
    {rule && <p className="mt-1 text-[10px] opacity-60">{rule}</p>}
  </div>
}
