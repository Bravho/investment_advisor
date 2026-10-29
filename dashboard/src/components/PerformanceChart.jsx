import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { money, number } from '../utils/format'
import { Card, SectionTitle, ServiceError, Skeleton } from './UI'

function chartData(data) {
  const rows = data?.series || data?.history || data?.performance_history || []
  if (rows.length) return rows.map(row => ({ date: row.date || row.record_date, portfolio: Number(row.portfolio ?? row.total_value_thb), SET: Number(row.SET ?? row.set_index), SP500: Number(row.SP500 ?? row.sp500) }))
  const portfolio = Number(data?.total_return_pct || 0)
  return [{ date: 'Start', portfolio: 0, SET: 0, SP500: 0 }, { date: 'Now', portfolio, SET: Number(data?.benchmark_comparison?.SET?.return || 0), SP500: Number(data?.benchmark_comparison?.SP500?.return || 0) }]
}

export default function PerformanceChart({ data, loading, error, retry, days, setDays }) {
  if (loading) return <Skeleton className="h-[420px]" />
  return <Card><SectionTitle title="ผลตอบแทนพอร์ต" subtitle="Portfolio performance vs benchmarks" action={<div className="flex rounded-lg bg-[#121620] p-1">{[7, 30, 90].map(value => <button key={value} onClick={() => setDays(value)} className={`rounded-md px-3 py-1.5 text-xs ${days === value ? 'bg-blue-500 text-white' : 'text-slate-500'}`}>{value}D</button>)}</div>} />
    {error ? <ServiceError retry={retry} /> : <><div className="mb-4 grid grid-cols-3 gap-2">{[['Return', `${number(data?.total_return_pct)}%`], ['Sharpe', number(data?.sharpe_ratio)], ['Max drawdown', `${number(data?.max_drawdown)}%`]].map(([key, value]) => <div key={key} className="rounded-xl bg-[#121620] p-3"><p className="text-[10px] text-slate-500">{key}</p><p className="mt-1 text-sm font-semibold text-white">{value}</p></div>)}</div><div className="h-72"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chartData(data)}><defs><linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10b981" stopOpacity={0.25} /><stop offset="100%" stopColor="#10b981" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#2a2f3e" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tickFormatter={value => `${number(value, 0)}%`} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#121620', border: '1px solid #2a2f3e', borderRadius: 10 }} formatter={(value, name) => [data?.series?.length ? money(value) : `${number(value)}%`, name]} /><Legend wrapperStyle={{ fontSize: 11 }} /><Area type="monotone" dataKey="portfolio" stroke="#10b981" fill="url(#portfolioFill)" strokeWidth={2} /><Line type="monotone" dataKey="SET" stroke="#3b82f6" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="SP500" stroke="#a78bfa" dot={false} strokeWidth={2} /></ComposedChart></ResponsiveContainer></div></>}
  </Card>
}
