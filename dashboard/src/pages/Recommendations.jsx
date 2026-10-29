import { Award, Bot, Crosshair, TrendingUp } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import RecommendationTable from '../components/RecommendationTable'
import StatCard from '../components/StatCard'
import { Card, SectionTitle, ServiceError, Skeleton } from '../components/UI'
import { useAccuracy, useRecommendations } from '../hooks/useAnalytics'
import { number } from '../utils/format'

const accuracyData = object => Object.entries(object || {}).map(([name, value]) => ({ name, accuracy: Number(value) * (Number(value) <= 1 ? 100 : 1) }))

function AccuracyChart({ title, data }) {
  return <Card><SectionTitle title={title} /><div className="h-64"><ResponsiveContainer><BarChart data={data}><CartesianGrid stroke="#2a2f3e" vertical={false} /><XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} formatter={value => `${number(value)}%`} /><Bar dataKey="accuracy" fill="#10b981" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></div></Card>
}

export default function Recommendations() {
  const accuracy = useAccuracy()
  const history = useRecommendations()
  const bestModel = Object.entries(accuracy.data?.accuracy_by_model || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || '-'
  const overall = Number(accuracy.data?.overall_accuracy || 0) * 100
  return <div className="space-y-6"><div><h2 className="text-2xl font-semibold text-white">คำแนะนำการลงทุน</h2><p className="mt-1 text-sm text-slate-500">Recommendation quality and history</p></div>
    {accuracy.error ? <ServiceError retry={accuracy.refetch} /> : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><StatCard label="ความแม่นยำรวม" sublabel="Overall accuracy" value={`${number(overall)}%`} detail={`${accuracy.data?.total_recommendations_reviewed || 0} reviewed`} icon={Crosshair} tone="green" loading={accuracy.loading} /><StatCard label="โมเดลดีที่สุด" sublabel="Best model" value={bestModel} detail="By historical accuracy" icon={Bot} tone="blue" loading={accuracy.loading} /><StatCard label="Ticker เด่น" sublabel="Best ticker" value={accuracy.data?.best_performing_ticker || '-'} detail="Best average outcome" icon={Award} tone="yellow" loading={accuracy.loading} /><StatCard label="ผลตอบแทนเมื่อถูก" sublabel="Avg return when correct" value={`${number(accuracy.data?.avg_return_when_correct)}%`} detail="Reviewed recommendations" icon={TrendingUp} tone="green" loading={accuracy.loading} /></div>}
    <RecommendationTable items={history.data} loading={history.loading} error={history.error} retry={history.refetch} />
    {accuracy.loading ? <Skeleton className="h-80" /> : <div className="grid gap-6 xl:grid-cols-2"><AccuracyChart title="Accuracy by action" data={accuracyData(accuracy.data?.accuracy_by_action)} /><AccuracyChart title="Accuracy by LLM model" data={accuracyData(accuracy.data?.accuracy_by_model)} /></div>}
  </div>
}
