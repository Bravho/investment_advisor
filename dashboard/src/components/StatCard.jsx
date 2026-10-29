import { Card, Skeleton } from './UI'

export default function StatCard({ label, sublabel, value, detail, icon: Icon, tone = 'blue', loading }) {
  const tones = { green: 'text-emerald-400 bg-emerald-500/10', red: 'text-red-400 bg-red-500/10', yellow: 'text-amber-400 bg-amber-500/10', gray: 'text-slate-400 bg-slate-500/10', blue: 'text-blue-400 bg-blue-500/10' }
  if (loading) return <Skeleton className="h-32" />
  return <Card className="relative overflow-hidden">
    <div className="flex items-start justify-between"><div><p className="text-xs text-slate-400">{label}</p><p className="text-[10px] text-slate-600">{sublabel}</p></div>{Icon && <div className={`rounded-xl p-2 ${tones[tone]}`}><Icon size={18} /></div>}</div>
    <p className={`mt-5 text-2xl font-semibold ${tones[tone].split(' ')[0]}`}>{value}</p>
    <p className="mt-1 text-xs text-slate-500">{detail}</p>
  </Card>
}
