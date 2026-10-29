import { Activity, CircleGauge, Landmark, Wallet } from 'lucide-react'
import BriefPanel from '../components/BriefPanel'
import HoldingsTable from '../components/HoldingsTable'
import OpportunityPanel from '../components/OpportunityPanel'
import AdvisoryCandidatesPanel from '../components/AdvisoryCandidatesPanel'
import StatCard from '../components/StatCard'
import { ServiceError } from '../components/UI'
import { useBrief } from '../hooks/useBrief'
import { useOpportunities } from '../hooks/useOpportunities'
import { useAdvisoryCandidates } from '../hooks/useAdvisoryCandidates'
import { useFactors, useRiskReport, useWatchlist } from '../hooks/usePhase3'
import WatchlistPanel from '../components/WatchlistPanel'
import FactorsPanel from '../components/FactorsPanel'
import RiskPanel from '../components/RiskPanel'
import SignalsPanel from '../components/SignalsPanel'
import { useSignals, useTradePlans } from '../hooks/usePhase4'
import { usePerformance, usePortfolio, useRisk } from '../hooks/usePortfolio'
import { money, normalizeRisk, number, valueOf } from '../utils/format'

export default function Dashboard() {
  const portfolio = usePortfolio()
  const performance = usePerformance(1, 60000)
  const risk = useRisk()
  const opportunities = useOpportunities()
  const advisory = useAdvisoryCandidates()
  const brief = useBrief()
  const watch = useWatchlist()
  const factors = useFactors()
  const riskReport = useRiskReport()
  const signals = useSignals()
  const tradePlans = useTradePlans()
  const pnl = Number(valueOf(performance.data, ['daily_pnl_thb', 'pnl_thb'], portfolio.data?.total_unrealized_pnl_thb || 0))
  const pnlPct = Number(valueOf(performance.data, ['daily_pnl_pct', 'total_return_pct']))
  const riskScore = normalizeRisk(valueOf(risk.data, ['portfolio_risk_score', 'risk_score'], brief.data?.portfolio_risk_score))
  const riskTone = riskScore < 33 ? 'green' : riskScore < 66 ? 'yellow' : 'red'
  const mood = brief.data?.macro_mood || 'unknown'
  const moodTone = mood === 'risk-on' ? 'green' : mood === 'risk-off' ? 'red' : 'gray'
  return <div className="space-y-6">
    <div><h2 className="text-2xl font-semibold text-white">ภาพรวมการลงทุน</h2><p className="mt-1 text-sm text-slate-500">Investment overview · refreshes every 60 seconds</p></div>
    {portfolio.error && !portfolio.data ? <ServiceError retry={portfolio.refetch} /> : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="มูลค่าพอร์ตรวม" sublabel="Total Portfolio Value" value={money(portfolio.data?.total_value_thb)} detail={`Base currency: ${portfolio.data?.base_currency || 'THB'}`} icon={Wallet} tone="blue" loading={portfolio.loading} />
      <StatCard label="กำไร/ขาดทุนวันนี้" sublabel="Daily P&L" value={money(pnl)} detail={`${pnlPct >= 0 ? '+' : ''}${number(pnlPct)}%`} icon={Activity} tone={pnl >= 0 ? 'green' : 'red'} loading={performance.loading} />
      <StatCard label="คะแนนความเสี่ยง" sublabel="Portfolio Risk Score" value={`${number(riskScore, 0)} / 100`} detail={riskScore < 33 ? 'Low risk' : riskScore < 66 ? 'Moderate risk' : 'High risk'} icon={CircleGauge} tone={riskTone} loading={risk.loading} />
      <StatCard label="อารมณ์ตลาด" sublabel="Market Mood" value={mood} detail="Macro sentiment" icon={Landmark} tone={moodTone} loading={brief.loading} />
    </div>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px_340px]"><HoldingsTable holdings={portfolio.data?.holdings} loading={portfolio.loading} error={portfolio.error} retry={portfolio.refetch} /><OpportunityPanel opportunities={opportunities.data} loading={opportunities.loading} error={opportunities.error} retry={opportunities.refetch} /><AdvisoryCandidatesPanel payload={advisory.data} loading={advisory.loading} error={advisory.error} retry={advisory.refetch} /></div>
    <BriefPanel brief={brief.data} loading={brief.loading} error={brief.error} retry={brief.refetch} />
    <SignalsPanel payload={signals.data} plans={tradePlans.data} loading={signals.loading} error={signals.error} retry={signals.refetch} />
    <FactorsPanel payload={factors.data} loading={factors.loading} error={factors.error} retry={factors.refetch} />
    <RiskPanel report={riskReport.data} loading={riskReport.loading} error={riskReport.error} retry={riskReport.refetch} />
    <WatchlistPanel payload={watch.data} loading={watch.loading} error={watch.error} retry={watch.refetch} />
  </div>
}
