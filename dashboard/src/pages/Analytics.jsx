import { AlertTriangle, CheckCircle2, Lock, Scale, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import AllocationChart from '../components/AllocationChart'
import PerformanceChart from '../components/PerformanceChart'
import RiskBreakdown from '../components/RiskBreakdown'
import { Badge, Card, SectionTitle } from '../components/UI'
import { portfolioClient } from '../config/api'
import { usePerformance, usePortfolio, useRisk } from '../hooks/usePortfolio'
import { money } from '../utils/format'

export default function Analytics() {
  const [days, setDays] = useState(30)
  const [plan, setPlan] = useState(null)
  const [planning, setPlanning] = useState(false)
  const [approving, setApproving] = useState(false)
  const performance = usePerformance(days)
  const portfolio = usePortfolio(0)
  const risk = useRisk(0)
  const generate = async () => {
    setPlanning(true)
    try { setPlan((await portfolioClient.post('/portfolio/rebalance')).data) } catch { setPlan({ error: true }) } finally { setPlanning(false) }
  }
  const approve = async () => {
    if (!plan?.plan_id) return
    setApproving(true)
    try {
      const { data } = await portfolioClient.post(`/portfolio/rebalance/approve?plan_id=${encodeURIComponent(plan.plan_id)}`)
      setPlan(data.plan || { ...plan, ...data, actionable: true, human_approval_status: 'approved' })
    } catch {
      setPlan(prev => prev ? { ...prev, approve_error: true } : prev)
    } finally {
      setApproving(false)
    }
  }
  const actionable = Boolean(plan?.actionable)
  return <div className="space-y-6"><div><h2 className="text-2xl font-semibold text-white">วิเคราะห์พอร์ต</h2><p className="mt-1 text-sm text-slate-500">Portfolio analytics and advisory rebalancing (human-approve gated)</p></div>
    <PerformanceChart {...performance} days={days} setDays={setDays} />
    <div className="grid gap-6 xl:grid-cols-2"><RiskBreakdown risk={risk.data} holdings={portfolio.data?.holdings} loading={risk.loading || portfolio.loading} error={risk.error} retry={risk.refetch} /><AllocationChart holdings={portfolio.data?.holdings} targets={plan?.target_allocations} loading={portfolio.loading} /></div>
    <Card><SectionTitle title="แผนปรับสมดุลพอร์ต" subtitle="Advisory rebalancing plan — approve to unlock actionable display (no auto-trade)" action={<button onClick={generate} disabled={planning} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-[#07140f] disabled:opacity-50"><Scale size={14} />{planning ? 'Generating...' : 'Generate Rebalancing Plan'}</button>} />
      {!plan ? <p className="py-10 text-center text-sm text-slate-500">กดปุ่มเพื่อวิเคราะห์สัดส่วนและสร้างแผนซื้อขาย (advisory)</p> : plan.error ? <p className="py-8 text-center text-sm text-red-400">Service unavailable</p> : <>
        <div className={`mb-4 flex flex-wrap items-center gap-3 rounded-xl border p-3 text-xs ${actionable ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
          {actionable ? <ShieldCheck size={14} /> : <Lock size={14} />}
          <span>{actionable ? 'Human-approved for display — still advisory; no trades executed.' : 'Pending human approval — suggestions shown as advisory only.'}</span>
          {plan.plan_id && <Badge tone={actionable ? 'green' : 'amber'}>{plan.human_approval_status || 'pending'}</Badge>}
          {!actionable && plan.plan_id && (
            <button onClick={approve} disabled={approving} className="ml-auto rounded-lg bg-amber-400 px-3 py-1.5 text-[11px] font-semibold text-[#1a1408] disabled:opacity-50">
              {approving ? 'Approving...' : 'Approve for display'}
            </button>
          )}
        </div>
        {plan.approve_error && <p className="mb-3 text-xs text-red-400">Approve failed — retry or regenerate the plan.</p>}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{plan.trades?.length ? plan.trades.map((trade, index) => <div key={`${trade.ticker}-${index}`} className={`rounded-xl border p-4 ${trade.actionable ? 'border-emerald-500/30 bg-[#121620]' : 'border-[#2a2f3e] bg-[#121620] opacity-90'}`}><div className="flex items-center justify-between"><Badge tone={trade.action === 'buy' ? 'green' : 'red'}>{trade.action}</Badge><div className="flex items-center gap-2">{trade.validated && <span className="flex items-center gap-1 text-[10px] text-emerald-400"><CheckCircle2 size={12} /> Validated</span>}{trade.actionable ? <Badge tone="green">actionable</Badge> : <Badge tone="yellow">advisory</Badge>}</div></div><p className="mt-4 text-lg font-bold text-white">{trade.ticker}</p><p className="text-sm text-slate-300">{money(trade.amount_thb)}</p><p className="mt-3 text-xs leading-5 text-slate-500">{trade.reason}</p>{trade.sentiment_conflict && <p className="mt-3 flex items-center gap-1 text-xs text-amber-400"><AlertTriangle size={13} /> Sentiment conflict</p>}</div>) : <p className="col-span-full py-8 text-center text-sm text-emerald-400">พอร์ตสมดุลดีแล้ว ไม่จำเป็นต้องปรับสัดส่วน</p>}</div>{plan.llm_narrative && <div className="mt-5 rounded-xl bg-blue-500/5 p-4 text-sm leading-6 text-slate-300">{plan.llm_narrative}</div>}</>}
    </Card>
  </div>
}
