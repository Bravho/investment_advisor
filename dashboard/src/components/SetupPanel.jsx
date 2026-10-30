import { Fragment, useState } from 'react'
import { Badge, Card, SectionTitle, ServiceError, Skeleton } from './UI'
import { number } from '../utils/format'

// 2026-10-30: momentum_base_swing - swing/position adaptation of Tho's lesson (docs/lessons/momentum_base_setup.md).
// Read-only: screen + levels + backtest. No order buttons exist; plans appear in Trade plans (approve = log decision only).
const fmt = (v) => v == null ? '-' : Number(v).toPrecision(4).replace(/\.?0+$/, '')
const pc = (v) => v == null ? '-' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`
const TONE = { triggered_today: 'green', at_support_wait_trigger: 'green', extended_wait_pullback: 'yellow', in_trade: 'blue', base_forming: 'gray', weekly_not_ok: 'gray', no_setup: 'gray', fails_screen: 'gray' }
const LABEL = { triggered_today: 'triggered today', at_support_wait_trigger: 'at support · wait trigger', extended_wait_pullback: 'extended · wait pullback', in_trade: 'setup running', base_forming: 'base forming', weekly_not_ok: 'weekly not ok', no_setup: 'strong, no setup', fails_screen: 'fails screen' }

export default function SetupPanel({ payload, loading, error, retry }) {
  const [open, setOpen] = useState(null)
  const [all, setAll] = useState(false)
  if (loading) return <Skeleton className="h-64" />
  if (error || !payload) return <Card><SectionTitle title="Momentum base setup" subtitle="swing" /><ServiceError retry={retry} compact /></Card>
  const items = (payload.items || []).filter(i => all || i.state !== 'fails_screen')
  const bt = payload.backtest || {}
  const lp = bt.live_params || {}
  return <Card>
    <SectionTitle title="Momentum + base (swing)" subtitle={`Tho's lesson, swing adaptation · weekly trend → daily trigger · screen as of ${payload.as_of || '-'}`}
      action={<div className="flex gap-1"><Badge tone="green">{(payload.items || []).filter(i => ['triggered_today', 'at_support_wait_trigger'].includes(i.state)).length} actionable</Badge>
        <Badge tone="gray">{(payload.items || []).filter(i => i.passed_screen).length} pass screen</Badge>
        <button onClick={() => setAll(!all)} className="rounded bg-slate-800 px-2 text-[10px] text-slate-300">{all ? 'hide fails' : 'show all'}</button></div>} />
    {bt.comparison && <div className="mb-2 grid gap-2 md:grid-cols-2">{Object.entries(bt.comparison).map(([u, c]) => <div key={u} className="rounded-lg bg-[#141925] p-2 text-[10px] text-slate-400">
      <b className="text-slate-200">{u}</b> OOS walk-forward: {c.setup.trades} trades · hit {number((c.setup.hit_rate || 0) * 100, 0)}% · expectancy <b className="text-slate-200">{number(c.setup.expectancy_r, 2)}R</b> · PF {number(c.setup.profit_factor, 2)} · CAGR {number((c.setup.cagr || 0) * 100, 1)}% · Sharpe {number(c.setup.sharpe, 2)} · maxDD {number((c.setup.max_drawdown || 0) * 100, 1)}%
      <br />best existing: {c.best_existing} (Sharpe {number(c.existing?.[c.best_existing]?.sharpe, 2)}, CAGR {number((c.existing?.[c.best_existing]?.cagr || 0) * 100, 1)}%) → <Badge tone={c.adds_value_oos ? 'green' : 'yellow'}>{c.adds_value_oos ? 'adds value' : 'kept separate'}</Badge></div>)}</div>}
    <div className="overflow-auto"><table className="w-full text-[11px]">
      <thead className="text-[10px] uppercase text-slate-500"><tr><th className="text-left">Ticker</th><th className="text-left">State</th><th className="text-right">RS%</th><th className="text-right">1m/3m/6m</th><th className="text-center">Wk</th><th className="text-center">Base</th><th className="text-right">Support zone</th><th className="text-right">Trigger</th><th className="text-right">Stop</th><th className="text-right">Target</th></tr></thead>
      <tbody>{items.map(i => <Fragment key={i.ticker}>
        <tr className="cursor-pointer border-t border-slate-800/80 hover:bg-[#141925]" onClick={() => setOpen(open === i.ticker ? null : i.ticker)}>
          <td className="py-1 text-slate-200">{i.ticker}{i.watchlist && <span className="ml-1 text-[9px] text-sky-400">watch</span>}</td>
          <td><Badge tone={TONE[i.state] || 'gray'}>{LABEL[i.state] || i.state}</Badge></td>
          <td className="text-right text-white">{number(i.rs_pct, 0)}</td>
          <td className="text-right text-slate-300 whitespace-nowrap">{pc(i.ret_1m)} / {pc(i.ret_3m)} / {pc(i.ret_6m)}</td>
          <td className="text-center">{i.weekly_ok ? '✓' : '·'}</td><td className="text-center">{i.base_ok ? '✓' : '·'} <span className="text-slate-500">{number(i.base_score, 0)}</span></td>
          <td className="text-right text-slate-300">{i.zone ? `${fmt(i.zone.low)}–${fmt(i.zone.high)}` : '-'}</td>
          <td className="text-right">{['triggered_today', 'at_support_wait_trigger'].includes(i.state) ? fmt(i.trigger?.price) : <span className="text-slate-600">-</span>}</td>
          <td className="text-right">{['triggered_today', 'at_support_wait_trigger'].includes(i.state) ? fmt(i.stop) : i.open_trade ? <span title="trailing level">{fmt(i.open_trade.trail_level)}↑</span> : '-'}</td>
          <td className="text-right">{fmt(i.target)}</td>
        </tr>
        {open === i.ticker && <tr><td colSpan={10} className="bg-[#0f131c] p-3 text-[11px] text-slate-300">
          <p>Price {fmt(i.price)} ({i.as_of}) · ATR14 {fmt(i.atr14)} · EMA9/21/50 {fmt(i.ema9)}/{fmt(i.ema21)}/{fmt(i.ema50)} · EMA21 5d slope {pc(i.ema21_slope5)} · ATR10/50 {number(i.atr_ratio, 2)} · typical bad gap {number((i.gap_q || 0) * 100, 1)}% · avg traded value {number(i.adv20 / 1e6, 0)}M</p>
          {i.breakout_date && <p>Breakout {i.breakout_date} over {fmt(i.breakout_level)}{i.pullback_date ? ` · first retest ${i.pullback_date}` : ''}{i.target_basis ? ` · target: ${i.target_basis}` : ''}</p>}
          {i.open_trade && <p className="text-sky-300">Setup triggered {i.open_trade.entry_date} at {fmt(i.open_trade.entry)} (initial stop {fmt(i.open_trade.initial_stop)}); now {number(i.open_trade.r_now, 2)}R; trail {i.open_trade.trail_rule} at {fmt(i.open_trade.trail_level)}. Model view only - not a position.</p>}
          {i.zone && <p>Zone evidence: {(i.zone.members || []).join(' · ')}</p>}
          <p className="text-slate-500">Levels: {(i.levels || []).map(l => `${fmt(l.level)} ${l.label}`).join(' · ')}</p>
          <p className="text-slate-500">Params: stop buffer {i.params?.atr_k}×ATR, exit {i.params?.exit} ({i.params?.source}). {i.trigger?.type}.</p>
        </td></tr>}
      </Fragment>)}</tbody></table></div>
    <p className="mt-2 text-[10px] text-slate-500">Swing/position only (weeks–months), daily bars, no intraday. Live params: TH {lp.TH?.exit}/{lp.TH?.atr_k}×ATR · US {lp.US?.exit}/{lp.US?.atr_k}×ATR. Advisory only - Tho places every order himself; plans go to Trade plans as PROPOSED. Survivorship bias in backtests.</p>
  </Card>
}
