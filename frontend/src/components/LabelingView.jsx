import { useEffect, useState } from 'react'
import axios from 'axios'

export default function LabelingView({ api }) {
  const [traces, setTraces] = useState([])
  const [labels, setLabels] = useState([])
  const [editing, setEditing] = useState(null) // {id, expected, query}
  const [exportMsg, setExportMsg] = useState('')

  const loadTraces = () => axios.get(`${api}/api/traces?limit=50`).then(r => setTraces(r.data)).catch(() => {})
  const loadLabels = () => axios.get(`${api}/api/labels`).then(r => setLabels(r.data)).catch(() => {})
  useEffect(() => { loadTraces(); loadLabels() }, [api])

  const proposeLabel = async (trace_id) => {
    const { data } = await axios.post(`${api}/api/labels`, { trace_id })
    await loadLabels()
    const lbl = (await axios.get(`${api}/api/labels`)).data.find(l => l.id === data.id)
    if (lbl) setEditing({ id: lbl.id, query: lbl.query, expected: JSON.stringify(lbl.expected, null, 2) })
  }

  const saveLabel = async (status) => {
    if (!editing) return
    let expected
    try { expected = JSON.parse(editing.expected) } catch { alert('Invalid JSON in expected'); return }
    await axios.put(`${api}/api/labels/${editing.id}`, { expected, label_status: status, labeled_by: 'reviewer' })
    setEditing(null); loadLabels()
  }

  const runExport = async () => {
    const { data } = await axios.post(`${api}/api/labels/export`)
    setExportMsg(data.added ? `Added ${data.added} case(s); dataset now v${data.version}` : 'No labeled cases to export.')
    loadLabels()
  }

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 lg:col-span-4 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Recent runs → propose label</h2>
        <div className="space-y-1 max-h-[40vh] overflow-y-auto">
          {traces.map(t => (
            <div key={t.trace_id} className="flex items-center gap-2 text-xs bg-gray-850 rounded-lg px-2 py-1.5">
              <span className="text-gray-400 truncate flex-1">{t.query}</span>
              <button onClick={() => proposeLabel(t.trace_id)}
                className="px-2 py-0.5 bg-indigo-700 hover:bg-indigo-600 rounded text-white shrink-0">label</button>
            </div>
          ))}
        </div>
        <button onClick={runExport}
          className="mt-4 w-full px-3 py-2 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-white text-sm">
          Export labeled → eval dataset
        </button>
        {exportMsg && <p className="text-[11px] text-emerald-400 mt-2">{exportMsg}</p>}
      </div>

      <div className="col-span-12 lg:col-span-4 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Edit expected behaviour</h2>
        {!editing ? (
          <p className="text-gray-600 text-sm">Propose a label from a run, then correct the expected behaviour here.</p>
        ) : (
          <div>
            <p className="text-xs text-gray-500 mb-2">{editing.query}</p>
            <textarea
              value={editing.expected}
              onChange={e => setEditing({ ...editing, expected: e.target.value })}
              rows={14}
              className="w-full bg-gray-950 text-gray-300 font-mono text-xs rounded-lg p-2 outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <div className="flex gap-2 mt-2">
              <button onClick={() => saveLabel('labeled')} className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded text-white text-sm">Save as labeled</button>
              <button onClick={() => saveLabel('rejected')} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-white text-sm">Reject</button>
            </div>
          </div>
        )}
      </div>

      <div className="col-span-12 lg:col-span-4 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">Labels ({labels.length})</h2>
        <div className="space-y-1.5 max-h-[60vh] overflow-y-auto">
          {labels.map(l => (
            <div key={l.id} className="text-xs bg-gray-850 rounded-lg px-2 py-1.5">
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  l.label_status === 'labeled' ? 'bg-emerald-900 text-emerald-300'
                    : l.label_status === 'rejected' ? 'bg-red-900 text-red-300' : 'bg-gray-700 text-gray-300'
                }`}>{l.label_status}</span>
                <span className="text-gray-400 truncate flex-1">{l.query}</span>
                {l.exported === 1 && <span className="text-[10px] text-indigo-400">exported</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
