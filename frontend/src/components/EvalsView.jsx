import { useEffect, useState } from 'react'
import axios from 'axios'

const pct = v => `${(Number(v || 0) * 100).toFixed(1)}%`
const verdictColor = v =>
  v === 'REGRESSED' ? 'text-red-400' : v === 'IMPROVED' ? 'text-emerald-400' : 'text-amber-300'

function RunCard({ run, role, onPick, picked }) {
  const s = run.summary || {}
  return (
    <button
      onClick={() => onPick(run.id)}
      className={`text-left rounded-lg p-3 text-xs w-full border ${
        picked ? 'border-indigo-500 bg-indigo-900/30' : 'border-gray-800 bg-gray-850 hover:bg-gray-800'
      }`}
    >
      <div className="flex items-center gap-2">
        {role && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-800 text-indigo-200">{role}</span>}
        <span className="text-gray-300 truncate flex-1">{run.agent_label}</span>
      </div>
      <div className="text-gray-500 mt-1 flex gap-3">
        <span>pass {pct(s.pass_rate)}</span>
        <span>q {Number(s.mean_overall_score || 0).toFixed(2)}</span>
        <span>${Number(s.total_cost_usd || 0).toFixed(5)}</span>
        <span className="ml-auto text-gray-600">{run.mode} · v{run.dataset_version}</span>
      </div>
    </button>
  )
}

export default function EvalsView({ api }) {
  const [runs, setRuns] = useState([])
  const [baseline, setBaseline] = useState(null)
  const [candidate, setCandidate] = useState(null)
  const [cmp, setCmp] = useState(null)

  const load = () => axios.get(`${api}/api/evals/runs?limit=50`).then(r => setRuns(r.data)).catch(() => {})
  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id) }, [api])

  useEffect(() => {
    if (baseline && candidate && baseline !== candidate) {
      axios.get(`${api}/api/evals/compare`, { params: { baseline, candidate } })
        .then(r => setCmp(r.data)).catch(() => setCmp(null))
    } else setCmp(null)
  }, [baseline, candidate, api])

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 lg:col-span-5 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-1">Eval Runs</h2>
        <p className="text-[11px] text-gray-600 mb-3">Pick a baseline, then a candidate to compare.</p>
        <div className="space-y-1.5 max-h-[70vh] overflow-y-auto">
          {runs.length === 0 && <p className="text-gray-600 text-sm">No eval runs yet. Run <code className="text-indigo-300">reliability.cli eval</code>.</p>}
          {runs.map(run => (
            <div key={run.id} className="flex gap-1">
              <RunCard run={run} role={baseline === run.id ? 'BASE' : candidate === run.id ? 'CAND' : null}
                picked={baseline === run.id || candidate === run.id}
                onPick={(id) => { if (!baseline) setBaseline(id); else if (baseline === id) setBaseline(null); else setCandidate(id === candidate ? null : id) }} />
            </div>
          ))}
        </div>
        {(baseline || candidate) && (
          <button onClick={() => { setBaseline(null); setCandidate(null) }}
            className="mt-3 text-xs text-gray-500 hover:text-gray-300">clear selection</button>
        )}
      </div>

      <div className="col-span-12 lg:col-span-7 bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-3">A/B Comparison</h2>
        {!cmp ? (
          <p className="text-gray-600 text-sm">Select two runs to see the paired statistical comparison.</p>
        ) : (
          <div className="text-sm">
            <div className={`text-lg font-bold mb-2 ${verdictColor(cmp.verdict)}`}>{cmp.verdict}</div>
            <div className="grid grid-cols-2 gap-3 mb-3 text-xs">
              <Metric label="Quality Δ" value={`${cmp.overall_delta >= 0 ? '+' : ''}${cmp.overall_delta.toFixed(3)}`}
                sub={`95% CI [${cmp.overall_delta_ci.low.toFixed(3)}, ${cmp.overall_delta_ci.high.toFixed(3)}]`} />
              <Metric label="Pass-rate" value={`${pct(cmp.baseline_pass_rate)} → ${pct(cmp.candidate_pass_rate)}`} />
              <Metric label="McNemar p" value={Number(cmp.mcnemar.p_value).toExponential(2)}
                sub={`${cmp.mcnemar.b_regressions} regressions / ${cmp.mcnemar.c_fixes} fixes`} />
              <Metric label="Wilcoxon p" value={Number(cmp.wilcoxon.p_value).toFixed(4)} />
            </div>
            <div className="bg-gray-950 rounded-lg p-3 mb-3 text-xs text-gray-400 space-y-1">
              {cmp.reasons.map((r, i) => <div key={i}>{r}</div>)}
            </div>
            <p className="text-[11px] text-gray-500 mb-1">Per-grader delta</p>
            <table className="w-full text-xs">
              <tbody>
                {cmp.per_grader.map(g => (
                  <tr key={g.grader} className="border-t border-gray-800">
                    <td className="py-1 text-gray-400">{g.grader}</td>
                    <td className={`py-1 text-right ${g.delta < 0 ? 'text-red-400' : g.delta > 0 ? 'text-emerald-400' : 'text-gray-500'}`}>
                      {g.delta >= 0 ? '+' : ''}{g.delta.toFixed(3)}
                    </td>
                    <td className="py-1 text-right text-gray-600">[{g.delta_ci.low.toFixed(2)}, {g.delta_ci.high.toFixed(2)}]</td>
                    <td className="py-1 text-right text-gray-500">{g.verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, sub }) {
  return (
    <div className="bg-gray-950 rounded-lg p-2">
      <div className="text-gray-500 text-[10px] uppercase">{label}</div>
      <div className="text-gray-200 font-mono">{value}</div>
      {sub && <div className="text-gray-600 text-[10px]">{sub}</div>}
    </div>
  )
}
