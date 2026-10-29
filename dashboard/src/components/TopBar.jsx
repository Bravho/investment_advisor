import { useEffect, useState } from 'react'
import { Clock3 } from 'lucide-react'

export default function TopBar() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(interval)
  }, [])
  const clock = new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Asia/Bangkok' }).format(now)
  return <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-[#2a2f3e] bg-[#0f1117]/90 px-5 pl-16 backdrop-blur lg:px-8 lg:pl-8">
    <div><h1 className="text-lg font-semibold text-white">Investment Advisor AI</h1><p className="text-xs text-slate-500">ระบบที่ปรึกษาการลงทุนอัจฉริยะ</p></div>
    <div className="hidden items-center gap-2 text-xs text-slate-400 sm:flex"><Clock3 size={14} className="text-emerald-400" />{clock} ICT</div>
  </header>
}
