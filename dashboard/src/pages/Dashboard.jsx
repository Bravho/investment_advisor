import { Activity, CircleGauge, Landmark, Wallet } from 'lucide-react'
import BriefPanel from '../components/BriefPanel'
import HoldingsTable from '../components/HoldingsTable'
import OpportunityPanel from '../components/OpportunityPanel'
import AdvisoryCandidatesPanel from '../components/AdvisoryCandidatesPanel'
import StatCard from '../components/StatCard'
import { ServiceError } from '../components/UI'
import { useBrief } from '../hooks/useBrief'
import { useMarketMood } from '../hooks/useNews'
import { useThaiWatchlist } from '../hooks/useThaiWatchlist'
import { useAdvisoryCandidates } from '../hooks/useAdvisoryCandidates'
import { useFactors, useRiskReport, useWatchlist } from '../hooks/usePhase3'
import WatchlistPanel from '../components/WatchlistPanel'
import FactorsPanel from '../components/FactorsPanel'
import RiskPanel from '../components/RiskPanel'
import SignalsPanel from '../components/SignalsPanel'
import BacktestPanel from '../components/BacktestPanel'
import TradePlansPanel from '../components/TradePlansPanel'
import PredictionsPanel from '../components/PredictionsPanel'
import Stamp from '../components/Stamp'
import ConstructionPanel from '../components/ConstructionPanel'
import AttributionPanel from '../components/AttributionPanel'
import { useAttribution, useConstruction, useBacktest, useJournal, usePaperTrades, usePredictionScoreboard, usePredictions, useSignalPerformance, useSignals, useTradePlans } from '../hooks/usePhase4'
import { usePerformance, usePortfolio, useRisk } from '../hooks/usePortfolio'
import { money, normalizeRisk, number, valueOf } from '../utils/format'

export default function Dashboard() {
  const portfolio = usePortfolio()
  const performance = usePerformance(1, 60000)
  const risk = useRisk()
  const watchlist = useThaiWatchlist()
  const advisory = useAdvisoryCandidates()
  const brief = useBrief()
  const mm = useMarketMood()
  const watch = useWatchlist()
  const factors = useFactors()
  const riskReport = useRiskReport()
  const signals = useSignals()
  const tradePlans = useTradePlans()
  const backtest = useBacktest()
  const sigPerf = useSignalPerformance()
  const paper = usePaperTrades()
  const journal = useJournal()
  const preds = usePredictions()
  const cons = useConstruction()
  const attr = useAttribution()
  const predBoard = usePredictionScoreboard()
  const pnl = Number(valueOf(performance.data, ['daily_pnl_thb', 'pnl_thb'], portfolio.data?.total_unrealized_pnl_thb || 0))
  const pnlPct = Number(valueOf(performance.data, ['daily_pnl_pct', 'total_return_pct']))
  const riskScore = normalizeRisk(valueOf(risk.data, ['portfolio_risk_score', 'risk_score'], brief.data?.portfolio_risk_score))
  const riskTone = riskScore < 33 ? 'green' : riskScore < 66 ? 'yellow' : 'red'
  // 2026-11-01: ONE verdict = price regime (what signals/construction use); news tone (crypto excluded) is the detail line
  const regime = mm.data?.verdict || 'unknown'
  const mood = regime === 'unknown' ? 'unknown' : `${regime.replace('_', '-')}${mm.data?.score != null ? ` (${number(mm.data.score, 2)})` : ''}`
  const moodTone = regime === 'risk_on' ? 'green' : regime === 'risk_off' ? 'red' : regime === 'neutral' ? 'yellow' : 'gray'
  const nt = mm.data?.news_tone
  const moodDetail = `ราคา: regime ${mm.data?.as_of ? new Date(mm.data.as_of).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' }) : ''} · ข่าว 24 ชม. (ไม่รวมคริปโต): ${nt?.mood || 'unknown'}${nt?.score != null ? ` ${nt.score > 0 ? '+' : ''}${number(nt.score, 2)}` : ''}`
  const maxTs = (arr, k) => (arr || []).reduce((m, x) => (x?.[k] && x[k] > m ? x[k] : m), '')
  const btAsOf = Object.values(backtest.data?.universes || {}).map(u => u?.run_at).filter(Boolean).sort().pop()
  return <div className="space-y-6">
    <div><h2 className="text-2xl font-semibold text-white">ภาพรวมการลงทุน</h2><p className="mt-1 text-sm text-slate-500">Investment overview · refreshes every 60 seconds</p></div>
    {portfolio.error && !portfolio.data ? <ServiceError retry={portfolio.refetch} /> : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="มูลค่าพอร์ตรวม" sublabel="Total Portfolio Value" value={money(portfolio.data?.total_value_thb)} detail={`Base currency: ${portfolio.data?.base_currency || 'THB'}`} icon={Wallet} tone="blue" loading={portfolio.loading} />
      <StatCard label="กำไร/ขาดทุนวันนี้" sublabel="Daily P&L" value={money(pnl)} detail={`${pnlPct >= 0 ? '+' : ''}${number(pnlPct)}%`} icon={Activity} tone={pnl >= 0 ? 'green' : 'red'} loading={performance.loading} />
      <StatCard label="คะแนนความเสี่ยง" sublabel="Portfolio Risk Score" value={`${number(riskScore, 0)} / 100`} detail={riskScore < 33 ? 'Low risk' : riskScore < 66 ? 'Moderate risk' : 'High risk'} icon={CircleGauge} tone={riskTone} loading={risk.loading} />
      <StatCard label="อารมณ์ตลาด" sublabel="Market Mood" value={mood} detail={moodDetail} icon={Landmark} tone={moodTone} loading={mm.loading} />
    </div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px_340px]"><HoldingsTable holdings={portfolio.data?.holdings} loading={portfolio.loading} error={portfolio.error} retry={portfolio.refetch} /><OpportunityPanel watchlist={watchlist.data} loading={watchlist.loading} error={watchlist.error} retry={watchlist.refetch} /><AdvisoryCandidatesPanel payload={advisory.data} loading={advisory.loading} error={advisory.error} retry={advisory.refetch} /></div>
    <Stamp items={[{ source: 'brief_generator', asOf: brief.data?.generated_at }]}><BriefPanel brief={brief.data} loading={brief.loading} error={brief.error} retry={brief.refetch} /></Stamp>
    <Stamp items={[{ source: 'signals · local LLM', asOf: maxTs(signals.data?.items, 'created_at') }]}><SignalsPanel payload={signals.data} plans={tradePlans.data} loading={signals.loading} error={signals.error} retry={signals.refetch} /></Stamp>
    <ConstructionPanel data={cons.data} loading={cons.loading} error={cons.error} retry={cons.refetch} />
    <AttributionPanel data={attr.data} loading={attr.loading} error={attr.error} retry={attr.refetch} />
    <Stamp items={[{ source: 'predictions (frozen)', asOf: maxTs(preds.data?.items, 'made_at') }, { source: 'scoreboard', asOf: predBoard.data?.model_weights?.[0]?.as_of, staleHours: 48 }]}><PredictionsPanel preds={preds.data} board={predBoard.data} loading={preds.loading || predBoard.loading} error={preds.error || predBoard.error} retry={preds.refetch} /></Stamp>
    <Stamp items={[{ source: 'trade plans · yfinance', asOf: maxTs(tradePlans.data?.plans, 'updated_at') }]}><TradePlansPanel plans={tradePlans.data} journal={journal.data} loading={tradePlans.loading} error={tradePlans.error} retry={tradePlans.refetch} /></Stamp>
    <Stamp items={[{ source: 'walk-forward backtest', asOf: btAsOf, staleHours: 24 * 8 }]}><BacktestPanel backtest={backtest.data} perf={sigPerf.data} paper={paper.data} loading={backtest.loading} error={backtest.error} retry={backtest.refetch} /></Stamp>
    <Stamp items={[{ source: 'market_factors', asOf: maxTs(factors.data?.factors, 'updated_at'), staleHours: 3 }]}><FactorsPanel payload={factors.data} loading={factors.loading} error={factors.error} retry={factors.refetch} /></Stamp>
    <Stamp items={[{ source: 'risk engine', asOf: riskReport.data?.run_at }, { source: 'prices', asOf: riskReport.data?.price_as_of, staleHours: 96 }]}><RiskPanel report={riskReport.data} loading={riskReport.loading} error={riskReport.error} retry={riskReport.refetch} /></Stamp>
    <Stamp items={[{ source: 'watchlist · yfinance', asOf: maxTs(watch.data?.items, 'price_as_of'), staleHours: 96 }]}><WatchlistPanel payload={watch.data} loading={watch.loading} error={watch.error} retry={watch.refetch} /></Stamp>
  </div>
}
