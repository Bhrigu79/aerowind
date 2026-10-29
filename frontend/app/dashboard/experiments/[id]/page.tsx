'use client'
import { useParams } from 'next/navigation'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { MetricComparison } from '@/components/experiments/MetricComparison'
import { ExperimentPipeline } from '@/components/experiments/ExperimentPipeline'
import { Badge } from '@/components/ui/Badge'
import { getExperiment, getExperiments } from '@/lib/api/experiments'
import { EXPERIMENT_TYPE_LABELS, formatDuration, relativeTime } from '@/lib/utils'
import type { ExperimentStatus, ExperimentType, Experiment, PipelineStageState } from '@/lib/types'

function generatePipelineForStatus(status: string): PipelineStageState[] {
  const stages: ('hypothesis'|'design'|'build'|'execute'|'measure'|'analyze'|'decide')[] = [
    'hypothesis', 'design', 'build', 'execute', 'measure', 'analyze', 'decide'
  ];

  const statusMap: Record<string, number> = {
    'pending': 1, 'building': 2, 'running': 3, 'measuring': 4, 'analyzing': 5, 'completed': 7, 'failed': 7
  };

  const currentIndex = statusMap[status] ?? 0;

  return stages.map((stage, i) => {
    let s: 'completed'|'running'|'queued'|'failed' = 'queued';
    if (i < currentIndex) s = 'completed';
    else if (i === currentIndex) s = 'running';

    if (status === 'failed' && i >= currentIndex) s = 'failed';
    if (status === 'completed') s = 'completed';

    return {
      stage,
      status: s,
    };
  });
}

const STATUS_VARIANT: Record<ExperimentStatus, 'default' | 'success' | 'warning' | 'error' | 'accent' | 'info'> = {
  pending:   'default',
  building:  'info',
  running:   'warning',
  measuring: 'accent',
  analyzing: 'accent',
  completed: 'success',
  failed:    'error',
  cancelled: 'default',
}

export default function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [exp, setExp] = useState<Experiment | null>(null)
  const [allExps, setAllExps] = useState<Experiment[]>([])

  useEffect(() => {
    getExperiment(id).then(setExp).catch(console.error)
    getExperiments().then(setAllExps).catch(console.error)
  }, [id])

  if (!exp) return <div className="p-8 text-dim">Loading...</div>

  const isRunning = exp.status === 'running'

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-border bg-surface/60 px-8 py-4 sticky top-0 z-30 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-dim hover:text-bright transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/>
              </svg>
            </Link>
            <div className="w-px h-4 bg-border" />
            <span className="text-xs font-mono text-dim">
              Experiment #{String(exp.sequence_number).padStart(2,'0')}
            </span>
            <div className="w-px h-4 bg-border" />
            <span className="text-sm font-medium text-bright">{exp.name}</span>
            <Badge variant={STATUS_VARIANT[exp.status]} pulse={isRunning}>
              {exp.status.toUpperCase()}
            </Badge>
            <Badge variant="warning">LOCAL DEMO</Badge>
          </div>
          <div className="text-xs font-mono text-dim">
            {EXPERIMENT_TYPE_LABELS[exp.experiment_type]}
            {exp.duration_seconds ? ` · ${formatDuration(exp.duration_seconds)}` : ''}
            {exp.started_at ? ` · started ${relativeTime(exp.started_at)}` : ''}
          </div>
        </div>
      </div>

      <div className="px-8 py-6 space-y-6">
        {/* Pipeline (always shown) */}
        <ExperimentPipeline
          stages={generatePipelineForStatus(exp.status)}
          experimentNumber={exp.sequence_number}
          hypothesis={exp.candidate_description || exp.name}
        />

        <div className="grid grid-cols-[1fr_340px] gap-5">
          {/* Main content */}
          <div className="space-y-5">
            {/* Hypothesis */}
            <div className="bg-panel border border-border rounded-xl p-5">
              <div className="text-xs font-mono text-dim uppercase tracking-wider mb-3">Hypothesis</div>
              <p className="text-base text-bright leading-relaxed">{exp.candidate_description}</p>
            </div>

            {/* Metric comparison */}
            <div>
              <h2 className="text-sm font-medium text-bright mb-3">Metric Comparison</h2>
              <MetricComparison
                baseline={exp.baseline_metrics}
                candidate={exp.candidate_metrics}
              />
            </div>

            {/* Conclusion */}
            {exp.conclusion && (
              <div className={`bg-panel border rounded-xl p-5 ${
                exp.hypothesis_confirmed === true  ? 'border-emerald/20' :
                exp.hypothesis_confirmed === false ? 'border-rose/20' :
                'border-border'
              }`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-xs font-mono text-dim uppercase tracking-wider">Conclusion</div>
                  {exp.hypothesis_confirmed != null && (
                    <Badge variant={exp.hypothesis_confirmed ? 'success' : 'error'}>
                      {exp.hypothesis_confirmed ? 'HYPOTHESIS CONFIRMED' : 'HYPOTHESIS REJECTED'}
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-bright leading-relaxed">{exp.conclusion}</p>
                {exp.adopted && (
                  <div className="flex items-center gap-2 mt-3 text-xs font-mono text-emerald">
                    <span>✓</span>
                    <span>Change adopted into production system</span>
                  </div>
                )}
                {exp.regression_detected && (
                  <div className="flex items-center gap-2 mt-3 text-xs font-mono text-rose">
                    <span>⚠</span>
                    <span>Regression detected — change rejected</span>
                  </div>
                )}
              </div>
            )}

            {/* Running state */}
            {isRunning && !exp.conclusion && (
              <div className="bg-panel border border-accent/20 rounded-xl p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                  <div className="text-sm text-accent-bright font-medium">Experiment in progress</div>
                </div>
                <p className="text-sm text-subtle">
                  Running 100-request benchmark against both baseline and candidate systems.
                  Results will appear here when measurement completes.
                </p>
                <div className="mt-4 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full w-2/5 bg-gradient-to-r from-accent-dim to-accent rounded-full animate-shimmer" style={{backgroundSize:'200% 100%'}} />
                </div>
              </div>
            )}
          </div>

          {/* Right: experiment metadata */}
          <div className="space-y-4">
            <div className="bg-panel border border-border rounded-xl p-4">
              <div className="text-xs font-mono text-dim uppercase tracking-wider mb-3">Experiment Details</div>
              <div className="space-y-2.5">
                {[
                  { label: 'Type', value: EXPERIMENT_TYPE_LABELS[exp.experiment_type] },
                  { label: 'Status', value: exp.status.toUpperCase() },
                  { label: 'Created', value: relativeTime(exp.created_at) },
                  { label: 'Started', value: exp.started_at ? relativeTime(exp.started_at) : '—' },
                  { label: 'Duration', value: formatDuration(exp.duration_seconds) },
                  { label: 'Source', value: (function(src) {
                      if (!src) return '—';
                      if (src === 'synthetic') return 'SIMULATION';
                      if (src === 'nebius') return 'REAL EXECUTION · NEBIUS';
                      if (src.includes('real')) return 'REAL EXECUTION';
                      return src.toUpperCase();
                    })(exp.candidate_metrics?.source) },
                  { label: 'Baseline requests', value: String(exp.baseline_metrics?.total_requests ?? '—') },
                  { label: 'Adopted', value: exp.adopted ? 'Yes' : 'No' },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-xs text-subtle">{label}</span>
                    <span className={`text-xs font-mono ${
                      value === 'Yes' ? 'text-emerald' : 'text-bright'
                    }`}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* All experiments nav */}
            <div className="bg-panel border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border text-xs font-mono text-dim uppercase tracking-wider">
                All Experiments
              </div>
              <div className="divide-y divide-border max-h-64 overflow-y-auto">
                {allExps.map(e => (
                  <Link key={e.id} href={`/dashboard/experiments/${e.id}`}
                    className={`flex items-center gap-3 px-4 py-2.5 hover:bg-raised/40 transition-colors ${
                      e.id === exp.id ? 'bg-raised/50' : ''
                    }`}>
                    <span className="text-2xs font-mono text-dim w-6">#{e.sequence_number}</span>
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                      e.adopted ? 'bg-emerald' :
                      e.hypothesis_confirmed === false ? 'bg-rose' :
                      e.status === 'running' ? 'bg-accent animate-pulse' :
                      'bg-muted'
                    }`} />
                    <span className="text-xs text-subtle truncate flex-1">{e.name}</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
