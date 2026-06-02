import { useEffect, useState } from 'react'
import axios from 'axios'

const severityColor = s =>
  s === 'critical' ? 'text-red-400' : s === 'warning' ? 'text-yellow-400' : 'text-gray-400'

export default function CostMetrics({ api }) {
  const [anomalies, setAnomalies] = useState([])

  useEffect(() => {
    const load = () => axios.get(`${api}/api/metrics/anomalies`).then(r => setAnomalies(r.data)).catch(() => {})
    load()
    const id = setInterval(load, 20000)
    return () => clearInterval(id)
  }, [api])

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 h-full">
      <h2 className="text-sm font-semibold text-gray-400 mb-3">Recent Anomaly Events</h2>
      {anomalies.length === 0 ? (
        <p className="text-gray-600 text-sm">No anomalies detected yet.</p>
      ) : (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {anomalies.map(a => (
            <div key={a.id} className="flex items-start gap-2 text-xs">
              <span className={`font-semibold shrink-0 ${severityColor(a.severity)}`}>
                {a.severity?.toUpperCase()}
              </span>
              <span className="text-gray-400">{a.description}</span>
              <span className="text-gray-600 shrink-0 ml-auto">{a.created_at?.slice(11, 16)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
