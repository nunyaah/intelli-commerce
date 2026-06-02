import ChatPanel from './components/ChatPanel'
import CostMetrics from './components/CostMetrics'
import HITLQueue from './components/HITLQueue'
import KPICards from './components/KPICards'
import RevenueChart from './components/RevenueChart'
import TicketHeatmap from './components/TicketHeatmap'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-sans">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-indigo-400 tracking-tight">IntelliCommerce</h1>
        <p className="text-xs text-gray-500">AI-Powered E-Commerce Intelligence · Live Data</p>
      </header>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12"><KPICards api={API} /></div>
        <div className="col-span-12 lg:col-span-8"><RevenueChart api={API} /></div>
        <div className="col-span-12 lg:col-span-4"><HITLQueue api={API} /></div>
        <div className="col-span-12 lg:col-span-6"><TicketHeatmap api={API} /></div>
        <div className="col-span-12 lg:col-span-6"><CostMetrics api={API} /></div>
        <div className="col-span-12"><ChatPanel api={API} /></div>
      </div>
    </div>
  )
}
