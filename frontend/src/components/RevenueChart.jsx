import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  CartesianGrid, Line, LineChart, ReferenceDot,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export default function RevenueChart({ api }) {
  const [data, setData] = useState([])
  const [anomalies, setAnomalies] = useState([])

  useEffect(() => {
    const load = () => {
      axios.get(`${api}/api/metrics/revenue-chart`).then(r => setData(r.data)).catch(() => {})
      axios.get(`${api}/api/metrics/anomalies`).then(r => setAnomalies(r.data)).catch(() => {})
    }
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [api])

  const anomalyHours = new Set(anomalies.map(a => a.created_at?.slice(0, 13)))
  const chartData = data.map(d => ({
    ...d,
    hour: d.hour?.slice(11, 16),
    isAnomaly: anomalyHours.has(d.hour?.slice(0, 13)),
  }))

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 mb-3">Revenue (48h)</h2>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="hour" tick={{ fill: '#6b7280', fontSize: 10 }} interval={3} />
          <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
          <Tooltip contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8 }} />
          <Line type="monotone" dataKey="revenue" stroke="#6366f1" dot={false} strokeWidth={2} />
          {chartData.filter(d => d.isAnomaly).map((d, i) => (
            <ReferenceDot key={i} x={d.hour} y={d.revenue} r={5} fill="#ef4444" stroke="none" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
