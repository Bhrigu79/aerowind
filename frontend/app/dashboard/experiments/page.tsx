'use client'
import Link from 'next/link'
import { ExperimentTimeline } from '@/components/experiments/ExperimentTimeline'
import { MetricComparison } from '@/components/experiments/MetricComparison'
import { Badge } from '@/components/ui/Badge'
import { useState, useEffect } from 'react'
import { getExperiments } from '@/lib/api/experiments'
import type { Experiment } from '@/lib/types'

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getExperiments()
      .then(data => {
        setExperiments(data)
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setError("Failed to load experiments")
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen p-8 text-dim flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-5 h-5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="text-sm font-mono uppercase tracking-widest">Loading Experiments...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return <div className="min-h-screen p-8 text-rose font-mono">{error}</div>
  }

  const running = experiments.filter(e => e.status === 'running')
  const completed = experiments.filter(e => e.status === 'completed')
  const adopted = experiments.filter(e => e.adopted)
  const rejected = experiments.filter(e => e.hypothesis_confirmed === false)

  // Find best result based on adoption or completion
  const bestExp = adopted.length > 0 ? adopted[adopted.length - 1] : completed.length > 0 ? completed[completed.length - 1] : null
  const baselineExp = experiments.length > 0 ? experiments[0] : null

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-border px-8 py-4 bg-surface/60 sticky top-0 z-30 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-white">Experiments</h1>
            <p className="text-xs text-subtle mt-0.5">
              {completed.length} completed · {running.length} running · {adopted.length} adopted
            </p>
          </div>
          <Link href="/dashboard/experiments/new"
            className="px-4 py-2 bg-accent/15 border border-accent/30 text-accent-bright text-sm rounded-lg hover:bg-accent/25 transition-all">
            + New Experiment
          </Link>
        </div>
      </div>

      <div className="px-8 py-6">
        {experiments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center border border-dashed border-border rounded-xl bg-panel">
            <div className="w-12 h-12 rounded-xl bg-surface/50 border border-border flex items-center justify-center mb-4 text-dim">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/>
              </svg>
            </div>
            <h3 className="text-sm font-medium text-bright mb-1">No experiments found</h3>
            <p className="text-xs text-subtle max-w-sm mb-6">Create your first experiment to start measuring performance and testing hypotheses against the baseline system.</p>
            <Link href="/dashboard/experiments/new" className="px-5 py-2.5 bg-accent text-white rounded-xl text-sm font-semibold hover:bg-accent-bright transition-all shadow-glow-sm">
              Create Experiment
            </Link>
          </div>
        ) : (
        <div className="grid grid-cols-[1fr_340px] gap-5">
          <div className="space-y-5">
            {/* Summary stats */}
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: 'Total', value: String(experiments.length), color: 'text-bright' },
                { label: 'Adopted', value: String(adopted.length), color: 'text-emerald' },
                { label: 'Rejected', value: String(rejected.length), color: 'text-rose' },
                { label: 'Running', value: String(running.length), color: 'text-amber' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-panel border border-border rounded-xl p-4 text-center">
                  <div className={`text-2xl font-mono font-bold ${color}`}>{value}</div>
                  <div className="text-xs text-dim mt-1">{label}</div>
                </div>
              ))}
            </div>

            <ExperimentTimeline experiments={experiments} projectId={experiments[0]?.project_id ?? ''} />
          </div>

          {/* Best result */}
          <div className="space-y-4">
            <div className="bg-panel border border-border rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-border">
                <h3 className="text-sm font-medium text-bright">Best Result</h3>
                <p className="text-xs text-subtle">
                  {bestExp ? `Experiment #${bestExp.sequence_number} — ${bestExp.adopted ? 'Adopted into production' : 'Completed'}` : 'No results yet'}
                </p>
              </div>
              <div className="p-4">
                {bestExp && baselineExp ? (
                  <MetricComparison
                    baseline={baselineExp.baseline_metrics}
                    candidate={bestExp.candidate_metrics}
                  />
                ) : (
                  <div className="text-center text-xs text-dim py-8">
                    Metrics will appear once an experiment completes.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        )}
      </div>
    </div>
  )
}
