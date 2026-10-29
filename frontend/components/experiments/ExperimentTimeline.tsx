'use client'
import { cn, relativeTime, EXPERIMENT_TYPE_LABELS } from '@/lib/utils'
import type { Experiment } from '@/lib/types'
import Link from 'next/link'

interface ExperimentTimelineProps {
  experiments: Experiment[]
  projectId: string
  className?: string
}

function ExperimentRow({ exp, isLast }: { exp: Experiment; isLast: boolean }) {
  const isRunning = exp.status === 'running' || exp.status === 'measuring' || exp.status === 'analyzing'
  const isAccepted = exp.adopted
  const isRejected = exp.hypothesis_confirmed === false
  const isFailed = exp.status === 'failed'
  const isBaseline = exp.experiment_type === 'baseline'

  return (
    <Link href={`/dashboard/experiments/${exp.id}`}
      className="group flex gap-4 relative hover:bg-raised/40 px-4 py-4 -mx-4 rounded-xl transition-colors">
      {/* Timeline line */}
      {!isLast && (
        <div className="absolute left-[26px] top-10 bottom-0 w-px bg-border" />
      )}

      {/* Status node */}
      <div className="relative z-10 flex-shrink-0 mt-0.5">
        <div className={cn(
          'w-5 h-5 rounded-full border-2 flex items-center justify-center',
          isRunning  ? 'border-accent bg-accent-glow' :
          isAccepted ? 'border-emerald bg-emerald-dim' :
          isFailed   ? 'border-rose bg-rose-dim' :
          isRejected ? 'border-rose/40 bg-muted' :
          isBaseline ? 'border-border bg-panel' :
          'border-border bg-panel'
        )}>
          {isRunning && <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />}
          {isAccepted && (
            <svg className="w-3 h-3 text-emerald" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7"/>
            </svg>
          )}
          {isRejected && !isFailed && (
            <svg className="w-3 h-3 text-rose" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12"/>
            </svg>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-2xs font-mono text-dim">#{String(exp.sequence_number).padStart(2,'0')}</span>
              <span className="text-2xs font-mono text-dim uppercase tracking-wider border border-border px-1.5 py-0.5 rounded">
                {EXPERIMENT_TYPE_LABELS[exp.experiment_type]}
              </span>
            </div>
            <div className="text-sm text-bright font-medium truncate">{exp.name}</div>
            {exp.candidate_description && (
              <div className="text-xs text-subtle mt-0.5 line-clamp-1">{exp.candidate_description}</div>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <span className={cn(
              'text-2xs font-mono px-1.5 py-0.5 rounded border uppercase tracking-wider',
              isRunning  ? 'text-accent-bright bg-accent-glow border-accent/20' :
              isAccepted ? 'text-emerald bg-emerald-dim border-emerald/20' :
              isFailed   ? 'text-rose bg-rose-dim border-rose/20' :
              isRejected ? 'text-rose/60 bg-muted/40 border-border' :
              isBaseline ? 'text-sky bg-sky-dim border-sky/20' :
              'text-dim bg-muted/40 border-border'
            )}>
              {isRunning ? 'RUNNING' : isAccepted ? 'ADOPTED' : isFailed ? 'FAILED' : isRejected ? 'REJECTED' : isBaseline ? 'BASELINE' : exp.status.toUpperCase()}
            </span>
            <span className="text-2xs text-dim font-mono">{relativeTime(exp.created_at)}</span>
          </div>
        </div>

        {/* Metric highlights for completed experiments */}
        {exp.status === 'completed' && exp.candidate_metrics && exp.baseline_metrics && (
          <div className="mt-2 flex gap-4">
            {exp.candidate_metrics.quality_score != null && exp.baseline_metrics.quality_score != null && (
              <span className="text-2xs font-mono">
                <span className="text-dim">Quality </span>
                <span className={exp.candidate_metrics.quality_score >= exp.baseline_metrics.quality_score ? 'text-emerald' : 'text-rose'}>
                  {exp.candidate_metrics.quality_score.toFixed(1)}%
                </span>
              </span>
            )}
            {exp.candidate_metrics.p95_latency_ms != null && (
              <span className="text-2xs font-mono">
                <span className="text-dim">P95 </span>
                <span className={exp.candidate_metrics.p95_latency_ms <= 2000 ? 'text-emerald' : 'text-amber'}>
                  {(exp.candidate_metrics.p95_latency_ms / 1000).toFixed(2)}s
                </span>
              </span>
            )}
            {exp.candidate_metrics.cost_per_request_usd != null && (
              <span className="text-2xs font-mono">
                <span className="text-dim">Cost </span>
                <span className={exp.candidate_metrics.cost_per_request_usd <= 0.03 ? 'text-emerald' : 'text-rose'}>
                  ${exp.candidate_metrics.cost_per_request_usd.toFixed(4)}
                </span>
              </span>
            )}
          </div>
        )}

        {/* Conclusion */}
        {exp.conclusion && (
          <p className="text-xs text-subtle mt-2 line-clamp-2 italic">&ldquo;{exp.conclusion}&rdquo;</p>
        )}
      </div>
    </Link>
  )
}

export function ExperimentTimeline({ experiments, projectId, className }: ExperimentTimelineProps) {
  const sorted = [...experiments].sort((a, b) => a.sequence_number - b.sequence_number)

  return (
    <div className={cn('bg-panel border border-border rounded-xl', className)}>
      <div className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-medium text-bright">Research Timeline</h3>
        <p className="text-xs text-subtle mt-0.5">Experiment history — scientific notebook</p>
      </div>
      <div className="px-4 py-2">
        {sorted.length === 0 ? (
          <div className="py-12 text-center">
            <div className="text-2xl text-dim mb-2">◎</div>
            <p className="text-sm text-subtle">No experiments yet.</p>
            <p className="text-xs text-dim mt-1">AEROWIND will begin experimenting once launched.</p>
          </div>
        ) : (
          sorted.map((exp, i) => (
            <ExperimentRow key={exp.id} exp={exp} isLast={i === sorted.length - 1} />
          ))
        )}
      </div>
    </div>
  )
}
