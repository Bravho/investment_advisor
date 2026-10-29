import { BarChart3, Compass, Crosshair, Home, Menu, MessageSquare, Newspaper, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'แดชบอร์ด', en: 'Dashboard', icon: Home },
  { to: '/analytics', label: 'วิเคราะห์พอร์ต', en: 'Analytics', icon: BarChart3 },
  { to: '/sentiment', label: 'ข่าวและอารมณ์ตลาด', en: 'Sentiment', icon: Newspaper },
  { to: '/recommendations', label: 'คำแนะนำ', en: 'Recommendations', icon: Crosshair },
  { to: '/discover', label: 'ค้นหาโอกาส', en: 'Explore / Discover', icon: Compass },
  { to: '/chat', label: 'คุยกับ AI', en: 'AI Chat', icon: MessageSquare },
]

export default function Sidebar({ open, setOpen }) {
  return <>
    <button onClick={() => setOpen(true)} className="fixed left-4 top-4 z-40 rounded-lg border border-[#2a2f3e] bg-[#1a1f2e] p-2 text-white lg:hidden"><Menu size={20} /></button>
    {open && <button aria-label="Close menu" onClick={() => setOpen(false)} className="fixed inset-0 z-40 bg-black/60 lg:hidden" />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r border-[#2a2f3e] bg-[#121620] transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="flex h-20 items-center justify-between border-b border-[#2a2f3e] px-5">
        <div><p className="font-semibold text-white">Investment Advisor</p><p className="text-xs text-emerald-400">AI Portfolio Intelligence</p></div>
        <button onClick={() => setOpen(false)} className="text-slate-400 lg:hidden"><X size={20} /></button>
      </div>
      <nav className="flex-1 space-y-2 p-4">
        {links.map(({ to, label, en, icon: Icon }) => <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-3 transition ${isActive ? 'bg-emerald-500/15 text-emerald-300' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}><Icon size={19} /><span><span className="block text-sm font-medium">{label}</span><span className="block text-[10px] opacity-60">{en}</span></span></NavLink>)}
      </nav>
      <div className="m-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-slate-400"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-400" />Local network mode</div>
    </aside>
  </>
}
