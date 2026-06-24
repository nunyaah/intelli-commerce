import { useEffect, useState } from 'react'
import axios from 'axios'

const actionStyle = a => ({
  block: 'bg-red-900 text-red-300',
  trip: 'bg-red-900 text-red-300',
  redact: 'bg-amber-900 text-amber-300',
  flag: 'bg-amber-900 text-amber-300',
  allow: 'bg-gray-800 text-gray-400',
}[a] || 'bg-gray-800 text-gray-400')

export default function GuardrailsView({ api }) {
  const [events, setEvents] = useState([])

  const load = () => axios.get(`${api}/api/guardrails/events?limit=200`).then(r => setEvents(r.data)).catch(() => {})
  useEffect(() => { load(); const id = setInterval(load, 6000); return () => clearInterval(id) }, [api])

  const counts = events.reduce((acc, e) => { acc[e.guard] = (acc[e.guard] || 0) + 1; return acc }, {})
  const blocking = events.filter(e => ['block', 'trip', 'redact'].includes(e.action)).length

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="flex items-center gap-4 mb-4">
        <h2 className="text-sm font-semibold text-gray-400">Guardrail Events</h2>
        <span className="text-xs text-gray-600">{events.length} total · {blocking} enforcement actions</span>
        <div className="ml-auto flex gap-2">
          {Object.entries(counts).map(([g, n]) => (
            <span key={g} className="text-[11px] px-2 py-0.5 rounded bg-gray-800 text-gray-400">{g}: {n}</span>
          ))}
        </div>
      </div>
      {events.length === 0 ? (
        <p className="text-gray-600 text-sm">No guardrail events yet. Try an unsafe query or run the demo.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-gray-600">
            <tr className="text-left">
              <th className="py-1">Time</th><th>Guard</th><th>Action</th><th>Severity</th><th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {events.map(e => (
              <tr key={e.id} className="border-t border-gray-800 align-top">
                <td className="py-1.5 text-gray-600 whitespace-nowrap">{(e.created_at || '').slice(11, 19)}</td>
                <td className="py-1.5 text-gray-300 font-mono">{e.guard}</td>
                <td className="py-1.5"><span className={`px-1.5 py-0.5 rounded ${actionStyle(e.action)}`}>{e.action}</span></td>
                <td className="py-1.5 text-gray-500">{e.severity}</td>
                <td className="py-1.5 text-gray-500 font-mono break-all max-w-md">{JSON.stringify(e.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
