import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { time } from '../utils/format'

export default function ChatMessage({ message }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  const assistant = message.role === 'assistant'
  return <div className={`flex ${assistant ? 'justify-start' : 'justify-end'}`}><div className={`group max-w-[86%] rounded-2xl px-4 py-3 md:max-w-[72%] ${assistant ? 'border border-[#2a2f3e] bg-[#1a1f2e]' : 'bg-emerald-500 text-[#07140f]'}`}>
    <div className={`text-sm leading-7 ${assistant ? 'text-slate-200' : 'font-medium'}`}>{assistant ? <ReactMarkdown components={{ ul: props => <ul className="my-2 list-disc pl-5" {...props} />, ol: props => <ol className="my-2 list-decimal pl-5" {...props} />, strong: props => <strong className="font-semibold text-white" {...props} /> }}>{message.content}</ReactMarkdown> : message.content}</div>
    <div className={`mt-2 flex items-center gap-2 text-[10px] ${assistant ? 'text-slate-600' : 'text-emerald-950/60'}`}><span>{time(message.timestamp)}</span>{assistant && <button onClick={copy} title="Copy response" className="opacity-0 transition group-hover:opacity-100">{copied ? <Check size={12} /> : <Copy size={12} />}</button>}</div>
  </div></div>
}
