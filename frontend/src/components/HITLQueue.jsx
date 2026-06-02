import { useEffect, useState } from 'react'
import axios from 'axios'

export default function HITLQueue({ api }) {
  const [queue, setQueue] = useState([])

  const load = () => axios.get(`${api}/api/hitl/queue`).then(r => setQueue(r.data)).catch(() => {})

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [api])

  const resolve = (id, action) =>
    axios.post(`${api}/api/hitl/${id}/resolve`, { action }).then(load)

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 h-full">
      <h2 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-2">
        HITL Queue
        {queue.length > 0 && (
          <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">{queue.length}</span>
        )}
      </h2>
      {queue.length === 0 ? (
        <p className="text-gray-600 text-sm">No pending approvals.</p>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto">
          {queue.map(item => (
            <div key={item.id} className="bg-gray-800 rounded-lg p-3 text-xs">
              <p className="text-red-400 font-semibold mb-1">ANOMALY DETECTED</p>
              <p className="text-gray-300 mb-2 line-clamp-3">{item.description}</p>
              <div className="flex gap-2">
                <button onClick={() => resolve(item.id, 'approve')} className="px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white">Approve</button>
                <button onClick={() => resolve(item.id, 'dismiss')} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-white">Dismiss</button>
                <button onClick={() => resolve(item.id, 'escalate')} className="px-2 py-1 bg-red-800 hover:bg-red-700 rounded text-white">Escalate</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
