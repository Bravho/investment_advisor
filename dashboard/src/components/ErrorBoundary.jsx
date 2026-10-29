import React from 'react'

export default class ErrorBoundary extends React.Component {
  state = { failed: false, message: '' }
  static getDerivedStateFromError(error) {
    return { failed: true, message: error?.message || 'Unknown rendering error' }
  }
  componentDidCatch(error, info) {
    console.error('Dashboard rendering error', error, info)
  }
  render() {
    if (this.state.failed) return <div className="flex min-h-screen items-center justify-center bg-[#0f1117] p-8"><div className="max-w-lg rounded-2xl border border-red-500/20 bg-[#1a1f2e] p-8 text-center"><p className="font-medium text-red-300">Dashboard rendering error</p><p className="mt-2 text-sm text-slate-400">{this.state.message}</p><button onClick={() => window.location.reload()} className="mt-5 rounded-lg bg-slate-700 px-4 py-2 text-xs text-white hover:bg-slate-600">Reload dashboard</button></div></div>
    return this.props.children
  }
}
