import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import CostMetrics from './components/CostMetrics'
import HITLQueue from './components/HITLQueue'
import KPICards from './components/KPICards'
import RevenueChart from './components/RevenueChart'
import TicketHeatmap from './components/TicketHeatmap'
import TraceExplorer from './components/TraceExplorer'
import EvalsView from './components/EvalsView'
import GuardrailsView from './components/GuardrailsView'
import LabelingView from './components/LabelingView'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'traces', label: 'Traces' },
  { id: 'evals', label: 'Evaluations' },
  { id: 'guardrails', label: 'Guardrails' },
  { id: 'hitl', label: 'HITL & Labeling' },
]

function Overview() {
  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12"><KPICards api={API} /></div>
      <div className="col-span-12 lg:col-span-8"><RevenueChart api={API} /></div>
      <div className="col-span-12 lg:col-span-4"><HITLQueue api={API} /></div>
      <div className="col-span-12 lg:col-span-6"><TicketHeatmap api={API} /></div>
      <div className="col-span-12 lg:col-span-6"><CostMetrics api={API} /></div>
      <div className="col-span-12"><ChatPanel api={API} /></div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState('overview')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-sans">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-indigo-400 tracking-tight">IntelliCommerce</h1>
        <p className="text-xs text-gray-500">
          AI Agent Reliability &amp; Evaluation · live tracing, evals, guardrails &amp; CI gating
        </p>
      </header>

      <nav className="flex gap-1 mb-6 border-b border-gray-800">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t.id
                ? 'bg-gray-900 text-indigo-300 border-b-2 border-indigo-400'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'overview' && <Overview />}
      {tab === 'traces' && <TraceExplorer api={API} />}
      {tab === 'evals' && <EvalsView api={API} />}
      {tab === 'guardrails' && <GuardrailsView api={API} />}
      {tab === 'hitl' && <LabelingView api={API} />}
    </div>
  )
}
