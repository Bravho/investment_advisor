import FactorHeatmap from '../components/FactorHeatmap'
import DeskPlans from '../components/DeskPlans'
import RiskPanel from '../components/RiskPanel'
import WatchlistPanel from '../components/WatchlistPanel'
import SignalsPanel from '../components/SignalsPanel'
import PredictionsPanel from '../components/PredictionsPanel'
import SetupPanel from '../components/SetupPanel'
import Stamp from '../components/Stamp'
import { Badge, SourceBadge } from '../components/UI'
import { useFactors, useRiskReport, useWatchlist } from '../hooks/usePhase3'
import { useJournal, useMomentumBase, usePredictionScoreboard, usePredictions, useSignals, useTradePlans } from '../hooks/usePhase4'
import { number } from '../utils/format'

const maxTs = (arr, k) => (arr || []).reduce((m, x) => (x?.[k] && x[k] > m ? x[k] : m), '')

// Pro #8 (2026-10-30): one-screen trading desk.
export default function Desk() {
  const risk = useRiskReport(), factors = useFactors(), watch = useWatchlist(), signals = useSignals()
  const plans = useTradePlans(120000), journal = useJournal(), preds = usePredictions(), board = usePredictionScoreboard(), setup = useMomentumBase()
  const s = risk.data?.summary || {}
  const reg = signals.data?.regime
  const boardAsOf = board.data?.model_weights?.[0]?.as_of
  return <div className="space-y-3">
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-[#151a24] px-3 py-2 text-xs">
      <b className="text-slate-100">Trading desk</b>
      <span>Value {number(s.value_thb, 0)} ฿</span>
      <span>VaR95 {number(s.hist_var95_thb, 0)} · ES95 {number(s.hist_es95_thb, 0)}</span>
      <span>Vol {number(s.vol_ann_pct, 1)}% · β(SET) {number(s.beta_set, 2)}</span>
      {reg && <Badge tone={reg.regime === 'risk_on' ? 'green' : reg.regime === 'risk_off' ? 'red' : 'yellow'}>{reg.regime} {number(reg.score, 2)}</Badge>}
      {(s.limit_breaches || []).length > 0 && <Badge tone="red">{s.limit_breaches.length} limit breaches</Badge>}
      {risk.data?.provisional && <Badge tone="yellow">PROVISIONAL holdings</Badge>}
      <span className="ml-auto flex gap-1"><SourceBadge source="risk" asOf={risk.data?.run_at} /><SourceBadge source="regime" asOf={reg?.created_at} /></span>
    </div>
    <div className="grid gap-3 xl:grid-cols-2">
      <Stamp items={[{ source: 'risk engine · yfinance', asOf: risk.data?.run_at }, { source: 'prices', asOf: s.price_as_of, staleHours: 96 }]}>
        <RiskPanel report={risk.data} loading={risk.loading} error={risk.error} retry={risk.refetch} /></Stamp>
      <FactorHeatmap report={risk.data} factors={factors.data} loading={risk.loading} error={risk.error} retry={risk.refetch} />
      <DeskPlans plans={plans.data} journal={journal.data} loading={plans.loading} error={plans.error} retry={plans.refetch} />
      <Stamp items={[{ source: 'signals · local LLM council', asOf: maxTs(signals.data?.items, 'created_at') }]}>
        <SignalsPanel payload={signals.data} plans={plans.data} loading={signals.loading} error={signals.error} retry={signals.refetch} /></Stamp>
      <Stamp items={[{ source: 'predictions (frozen)', asOf: maxTs(preds.data?.items || preds.data?.predictions, 'made_at') }, { source: 'scoreboard', asOf: boardAsOf, staleHours: 48 }]}>
        <PredictionsPanel preds={preds.data} board={board.data} loading={preds.loading || board.loading} error={preds.error || board.error} retry={preds.refetch} /></Stamp>
      <div className="xl:col-span-2"><Stamp items={[{ source: 'setup screen · yfinance daily', asOf: maxTs(setup.data?.items, 'created_at') }, { source: 'setup backtest', asOf: setup.data?.backtest?.run_at, staleHours: 24 * 8 }]}>
        <SetupPanel payload={setup.data} loading={setup.loading} error={setup.error} retry={setup.refetch} /></Stamp></div>
      <Stamp items={[{ source: 'watchlist prices · yfinance', asOf: maxTs(watch.data?.items, 'price_as_of'), staleHours: 96 }]}>
        <WatchlistPanel payload={watch.data} loading={watch.loading} error={watch.error} retry={watch.refetch} /></Stamp>
    </div>
  </div>
}
