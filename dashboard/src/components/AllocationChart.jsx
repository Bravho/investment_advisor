import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { number } from '../utils/format'
import { Card, SectionTitle, Skeleton } from './UI'

const COLORS = ['#10b981', '#3b82f6', '#a78bfa', '#f59e0b', '#64748b']
const defaults = { equity: 0.5, crypto: 0.15, bond: 0.25, cash: 0.1 }

export default function AllocationChart({ holdings = [], targets = defaults, loading }) {
  holdings = holdings || []
  targets = targets || defaults
  if (loading) return <Skeleton className="h-96" />
  const totals = holdings.reduce((acc, item) => ({ ...acc, [String(item.asset_class || 'other').toLowerCase()]: (acc[String(item.asset_class || 'other').toLowerCase()] || 0) + Number(item.market_value_thb || 0) }), {})
  const total = Object.values(totals).reduce((sum, value) => sum + value, 0)
  const current = Object.entries(totals).map(([name, value]) => ({ name, value: total ? value / total * 100 : 0 }))
  const target = Object.entries(targets).map(([name, value]) => ({ name, value: Number(value) * (Number(value) <= 1 ? 100 : 1) }))
  const pie = (data, title) => <div><p className="text-center text-xs font-medium text-slate-400">{title}</p><div className="h-56"><ResponsiveContainer><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70} paddingAngle={3}>{data.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}</Pie><Tooltip formatter={value => `${number(value)}%`} contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} /><Legend wrapperStyle={{ fontSize: 10 }} /></PieChart></ResponsiveContainer></div></div>
  return <Card><SectionTitle title="สัดส่วนสินทรัพย์" subtitle="Current vs target allocation" /><div className="grid grid-cols-2 gap-2">{pie(current.length ? current : [{ name: 'empty', value: 100 }], 'Current')}{pie(target, 'Target')}</div></Card>
}
