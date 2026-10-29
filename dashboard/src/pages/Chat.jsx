import { MessageSquarePlus, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ChatMessage from '../components/ChatMessage'
import { advisorClient } from '../config/api'

const quickPrompts = ['📊 วิเคราะห์พอร์ตของฉัน', '📈 โอกาสการลงทุนวันนี้', '⚖️ ควรรีบาลานซ์ไหม', '📰 ข่าวสำคัญวันนี้มีอะไรบ้าง']
const welcome = { id: 'welcome', role: 'assistant', content: 'สวัสดีครับ ผมคือ Investment Advisor AI พร้อมช่วยวิเคราะห์พอร์ต โอกาส และความเสี่ยงของคุณ', timestamp: new Date().toISOString() }

export default function Chat() {
  const [conversations, setConversations] = useState([{ id: 'default', title: 'บทสนทนาใหม่', messages: [welcome] }])
  const [activeId, setActiveId] = useState('default')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef(null)
  const active = conversations.find(item => item.id === activeId) || conversations[0]
  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), [active?.messages, sending])

  const updateMessages = (id, updater) => setConversations(items => items.map(item => item.id === id ? { ...item, messages: updater(item.messages) } : item))
  const createConversation = () => {
    const id = crypto.randomUUID()
    setConversations(items => [...items, { id, title: 'บทสนทนาใหม่', messages: [{ ...welcome, id: crypto.randomUUID(), timestamp: new Date().toISOString() }] }])
    setActiveId(id)
  }
  const send = async (text = input) => {
    const content = text.trim()
    if (!content || sending) return
    const conversationId = active.id
    const userMessage = { id: crypto.randomUUID(), role: 'user', content, timestamp: new Date().toISOString() }
    const history = [...active.messages, userMessage].slice(-10).map(({ role, content: messageContent }) => ({ role, content: messageContent }))
    setInput('')
    setSending(true)
    setConversations(items => items.map(item => item.id === conversationId ? { ...item, title: item.title === 'บทสนทนาใหม่' ? content.slice(0, 32) : item.title, messages: [...item.messages, userMessage] } : item))
    try {
      const { data } = await advisorClient.post('/advisors/message', { sender: 'dashboard', recipient: 'investment_advisor', intent: 'user_query', payload: { message: content, history } })
      updateMessages(conversationId, messages => [...messages, { id: crypto.randomUUID(), role: 'assistant', content: data.response || 'ไม่ได้รับคำตอบจากระบบ', timestamp: new Date().toISOString() }])
    } catch {
      updateMessages(conversationId, messages => [...messages, { id: crypto.randomUUID(), role: 'assistant', content: '**Service unavailable**\n\nไม่สามารถเชื่อมต่อ Investment Advisor ที่พอร์ต 8998 ได้ กรุณาลองใหม่อีกครั้ง', timestamp: new Date().toISOString() }])
    } finally { setSending(false) }
  }
  return <div className="-m-4 flex h-[calc(100vh-80px)] overflow-hidden md:-m-6 lg:-m-8">
    <aside className="hidden w-[260px] shrink-0 border-r border-[#2a2f3e] bg-[#121620] p-4 md:block"><button onClick={createConversation} className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-3 py-3 text-xs font-semibold text-[#07140f]"><MessageSquarePlus size={15} /> บทสนทนาใหม่</button><div className="mt-4 space-y-2">{conversations.map(item => <button key={item.id} onClick={() => setActiveId(item.id)} className={`w-full truncate rounded-xl px-3 py-3 text-left text-xs ${activeId === item.id ? 'bg-[#1a1f2e] text-white' : 'text-slate-500 hover:bg-white/5'}`}>{item.title}</button>)}</div></aside>
    <section className="flex min-w-0 flex-1 flex-col bg-[#0f1117]"><div className="border-b border-[#2a2f3e] px-5 py-4"><p className="font-medium text-white">AI Investment Advisor</p><p className="text-xs text-emerald-400"><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />Ready to analyze</p></div><div className="flex-1 overflow-y-auto p-4 md:p-6"><div className="mx-auto max-w-4xl space-y-5">{active.messages.map(message => <ChatMessage key={message.id} message={message} />)}{sending && <div className="flex"><div className="flex gap-1 rounded-2xl border border-[#2a2f3e] bg-[#1a1f2e] px-5 py-4">{[0, 1, 2].map(index => <span key={index} className="h-1.5 w-1.5 animate-bounce rounded-full bg-emerald-400" style={{ animationDelay: `${index * 150}ms` }} />)}</div></div>}<div ref={bottomRef} /></div></div><div className="border-t border-[#2a2f3e] bg-[#121620] p-4"><div className="mx-auto max-w-4xl"><div className="mb-3 flex gap-2 overflow-x-auto pb-1">{quickPrompts.map(prompt => <button key={prompt} onClick={() => send(prompt)} className="shrink-0 rounded-full border border-[#2a2f3e] bg-[#1a1f2e] px-3 py-2 text-[11px] text-slate-400 hover:border-emerald-500/40 hover:text-white">{prompt}</button>)}</div><form onSubmit={event => { event.preventDefault(); send() }} className="flex items-end gap-2 rounded-2xl border border-[#2a2f3e] bg-[#1a1f2e] p-2 focus-within:border-emerald-500/50"><textarea value={input} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send() } }} rows={1} placeholder="ถามเรื่องพอร์ต การลงทุน หรือข่าวตลาด..." className="max-h-28 flex-1 resize-none bg-transparent px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600" /><button type="submit" disabled={!input.trim() || sending} className="rounded-xl bg-emerald-500 p-3 text-[#07140f] disabled:opacity-30"><Send size={17} /></button></form></div></div></section>
  </div>
}
