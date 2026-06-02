import { useEffect, useRef, useState } from 'react'

const SUGGESTED = [
  "What are today's KPIs?",
  'Are there any anomalies right now?',
  'What are the most common support issues?',
  'Show me revenue for the last 7 days',
]

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${isUser ? 'bg-indigo-700 text-white' : 'bg-gray-800 text-gray-200'}`}>
        {msg.type === 'tool_call' ? (
          <span className="text-indigo-300 font-mono text-xs">
            Calling {msg.tool}({JSON.stringify(msg.args)})...
          </span>
        ) : (
          <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ api }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [threadId, setThreadId] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = async (text) => {
    const q = text || input.trim()
    if (!q || loading) return
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: q }])

    try {
      const res = await fetch(`${api}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q, thread_id: threadId }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const ev = JSON.parse(line.slice(6))
          if (ev.type === 'done') {
            if (ev.thread_id) setThreadId(ev.thread_id)
          } else if (ev.type === 'message') {
            setMessages(prev => [...prev, { role: 'assistant', content: ev.content }])
          } else if (ev.type === 'tool_call') {
            setMessages(prev => [...prev, { role: 'tool', type: 'tool_call', tool: ev.tool, args: ev.args }])
          } else if (ev.type === 'hitl_alert') {
            setMessages(prev => [...prev, { role: 'assistant', content: 'HITL Alert raised — check the queue.' }])
          }
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 flex flex-col h-[500px]">
      <div className="p-4 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-400">AI Analyst Chat</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-gray-600 text-sm mb-3">Ask a question or pick a suggestion:</p>
            {SUGGESTED.map(s => (
              <button key={s} onClick={() => send(s)} className="block w-full text-left text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg px-3 py-2">
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        {loading && (
          <div className="flex justify-start mb-3">
            <div className="bg-gray-800 rounded-xl px-4 py-2 text-sm text-gray-500 animate-pulse">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="p-4 border-t border-gray-800 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Ask about revenue, tickets, anomalies..."
          className="flex-1 bg-gray-800 text-gray-200 placeholder-gray-600 rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          Send
        </button>
      </div>
    </div>
  )
}
