import { useEffect, useState } from 'react'
import axios from 'axios'

function Card({ label, value, color }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color || 'text-white'}`}>{value}</p>
    </div>
  )
}

export default function KPICards({ api }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    const load = () => axios.get(`${api}/api/metrics/kpis`).then(r => setData(r.data)).catch(() => {})
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [api])

  if (!data) return <div className="text-gray-600 text-sm">Loading KPIs...</div>

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      <Card label="Revenue Today" value={`$${data.revenue_today?.toLocaleString()}`} color="text-green-400" />
      <Card label="Orders Today" value={data.orders_today} />
      <Card label="Avg Order Value" value={`$${data.avg_order_value}`} />
      <Card label="Fraud Flags" value={data.fraud_flags} color={data.fraud_flags > 5 ? 'text-red-400' : 'text-white'} />
      <Card label="Open Tickets" value={data.tickets_open} color={data.tickets_open > 20 ? 'text-yellow-400' : 'text-white'} />
      <Card label="Avg Resolution" value={`${data.avg_resolution_minutes}m`} />
    </div>
  )
}
