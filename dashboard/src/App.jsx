import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Analytics from './pages/Analytics'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Desk from './pages/Desk'
import Discover from './pages/Discover'
import Recommendations from './pages/Recommendations'
import Sentiment from './pages/Sentiment'

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  return <ErrorBoundary><div className="min-h-screen bg-[#0f1117] text-slate-200"><Sidebar open={menuOpen} setOpen={setMenuOpen} /><div className="lg:ml-[260px]"><TopBar /><main className="p-4 md:p-6 lg:p-8"><Routes><Route path="/" element={<Dashboard />} /><Route path="/desk" element={<Desk />} /><Route path="/analytics" element={<Analytics />} /><Route path="/sentiment" element={<Sentiment />} /><Route path="/recommendations" element={<Recommendations />} /><Route path="/discover" element={<Discover />} /><Route path="/chat" element={<Chat />} /></Routes></main></div></div></ErrorBoundary>
}
