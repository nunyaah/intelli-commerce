import { useEffect, useState } from 'react'
import axios from 'axios'

const fmtCost = c => `$${Number(c || 0).toFixed(6)}`
const fmtMs = ms => `${Math.round(ms || 0)}ms`

function SpanRow({ span }) {
  const kindColor = {
    llm: 'text-indigo-300',
    tool: 'text-emerald-300',
    guardrail: 'text-amber-300',
  }[span.kind] || 'text-gray-300'
  const attrs = span.attributes || {}
  return (
    <div className="border-l-2 border-gray-700 pl-3 py-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span className={`font-mono font-semibold ${kindColor}`}>{span.name}</span>
        <span className="text-gray-600 ml-auto">{fmtMs(span.duration_ms)}</span>
        {span.status === 'error' && <span className="text-red-400">error</span>}
      </div>
      {span.kind === 'llm' && (
        <div className="text-[11px] text-gray-500 mt-0.5">
          {attrs['gen_ai.usage.input_tokens'] || 0} in / {attrs['gen_ai.usage.output_tokens'] || 0} out ·{' '}
          {fmtCost(attrs['gen_ai.cost.usd'])}
        </div>
      )}
      {span.kind === 'tool' && (
        <div className="text-[11px] text-gray-500 mt-0.5 font-mono break-all">
          args: {JSON.stringify(attrs['gen_ai.tool.call.arguments'])}
          {attrs['gen_ai.tool.call.result'] && (
            <div className="text-gray-600 mt-0.5 line-clamp-2">
              → {String(attrs['gen_ai.tool.call.result']).slice(0, 200)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TraceExplorer({ api }) {
  const [traces, setTraces] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  const load = () => axios.get(`${api}/api/traces?limit=100`).then(r => setTraces(r.data)).catch(() => {})
  useEffect(() => { load(); const id = setInterval(load, 8000); return () => clearInterval(id) }, [api])
  useEffect(() => {
    if (!selected) return
    axios.get(`${api}/api/traces/${selected}`).then(r => setDetail(r.data)).catch(() => setDetail(null))
  }, [selected, api])

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 lg:col-span-5 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Trace Explorer · {traces.length} runs</h2>
        <div className="space-y-1 max-h-[70vh] overflow-y-auto">
          {traces.length === 0 && <p className="text-gray-600 text-sm">No traces yet — ask the agent something.</p>}
          {traces.map(t => (
            <button
              key={t.trace_id}
              onClick={() => setSelected(t.trace_id)}
              className={`block w-full text-left rounded-lg px-3 py-2 text-xs ${
                selected === t.trace_id ? 'bg-indigo-900/40 border border-indigo-700' : 'bg-gray-850 hover:bg-gray-800'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  t.source === 'live' ? 'bg-emerald-900 text-emerald-300' : 'bg-gray-700 text-gray-300'
                }`}>{t.source}</span>
                <span className="text-gray-300 truncate flex-1">{t.query}</span>
              </div>
              <div className="text-gray-600 mt-1 flex gap-3">
                <span>{t.num_tool_calls} tools</span>
                <span>{fmtCost(t.cost_usd)}</span>
                <span>{fmtMs(t.duration_ms)}</span>
                {t.error && <span className="text-red-400">error</span>}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="col-span-12 lg:col-span-7 bg-gray-900 rounded-xl border border-gray-800 p-4">
        {!detail ? (
          <p className="text-gray-600 text-sm">Select a trace to inspect its span tree and transcript.</p>
        ) : (
          <div>
            <h2 className="text-sm font-semibold text-gray-400 mb-1">Run {detail.trace_id.slice(0, 8)}</h2>
            <div className="flex gap-4 text-xs text-gray-500 mb-3">
              <span>{detail.input_tokens + detail.output_tokens} tokens</span>
              <span>{fmtCost(detail.cost_usd)}</span>
              <span>{fmtMs(detail.duration_ms)}</span>
              <span>{detail.num_llm_calls} LLM · {detail.num_tool_calls} tools</span>
            </div>
            <div className="bg-gray-950 rounded-lg p-3 mb-3">
              <p className="text-[11px] text-gray-500 mb-1">Question</p>
              <p className="text-sm text-gray-300">{detail.query}</p>
              <p className="text-[11px] text-gray-500 mt-2 mb-1">Answer</p>
              <p className="text-sm text-gray-300 whitespace-pre-wrap">{detail.final_answer}</p>
            </div>
            <p className="text-[11px] text-gray-500 mb-1">Span tree</p>
            <div className="space-y-0.5">
              {(detail.spans || []).map(s => <SpanRow key={s.span_id} span={s} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
