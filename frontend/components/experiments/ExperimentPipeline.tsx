'use client'
import { cn } from '@/lib/utils'
import type { PipelineStage, PipelineStageState, StageStatus } from '@/lib/types'

const STAGE_LABELS: Record<PipelineStage, string> = {
  hypothesis: 'Hypothesis',
  design:     'Design',
  build:      'Build',
  execute:    'Execute',
  measure:    'Measure',
  analyze:    'Analyze',
  decide:     'Decide',
}

const STAGE_ICONS: Record<PipelineStage, string> = {
  hypothesis: '⟡',
  design:     '◈',
  build:      '⬡',
  execute:    '▶',
  measure:    '◉',
  analyze:    '⊛',
  decide:     '✦',
}

function StageIndicator({ status }: { status: StageStatus }) {
  return (
    <span className={cn(
      'w-2.5 h-2.5 rounded-full flex-shrink-0',
      status === 'completed' ? 'bg-emerald' :
      status === 'running'   ? 'bg-accent animate-pulse' :
      status === 'failed'    ? 'bg-rose' :
      'bg-muted border border-border'
    )} />
  )
}

interface ExperimentPipelineProps {
  stages: PipelineStageState[]
  experimentNumber?: number
  hypothesis?: string
  className?: string
  compact?: boolean
}

export function ExperimentPipeline({
  stages, experimentNumber, hypothesis, className, compact = false
}: ExperimentPipelineProps) {
  const activeStage = stages.find(s => s.status === 'running')
  const completedCount = stages.filter(s => s.status === 'completed').length
  const progress = Math.round((completedCount / stages.length) * 100)

  return (
    <div className={cn('bg-panel border border-border rounded-xl overflow-hidden', className)}>
      {/* Header */}
      {!compact && (
        <div className="px-5 pt-5 pb-4 border-b border-border">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              {experimentNumber && (
                <span className="text-xs font-mono text-dim">
                  Experiment #{String(experimentNumber).padStart(2, '0')}
                </span>
              )}
              <span className={cn(
                'text-xs font-mono px-2 py-0.5 rounded-md border uppercase tracking-wider',
                activeStage
                  ? 'text-accent-bright bg-accent-glow border-accent/20'
                  : completedCount === stages.length
                  ? 'text-emerald bg-emerald-dim border-emerald/20'
                  : 'text-dim bg-muted/40 border-border'
              )}>
                {activeStage ? activeStage.stage.toUpperCase() : completedCount === stages.length ? 'COMPLETE' : 'QUEUED'}
              </span>
            </div>
            <span className="text-xs font-mono text-dim">{progress}%</span>
          </div>

          {hypothesis && (
            <p className="text-sm text-bright leading-relaxed mt-1">
              <span className="text-dim text-xs">Hypothesis: </span>
              {hypothesis}
            </p>
          )}

          {/* Progress bar */}
          <div className="mt-3 h-0.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-accent-dim to-accent transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Pipeline stages */}
      <div className={cn('px-5', compact ? 'py-3' : 'py-4')}>
        <div className="flex items-center gap-0">
          {stages.map((s, i) => (
            <div key={s.stage} className="flex items-center flex-1 min-w-0">
              {/* Stage node */}
              <div className="relative flex flex-col items-center group">
                <div className={cn(
                  'relative w-8 h-8 rounded-lg flex items-center justify-center text-sm transition-all duration-300 border',
                  s.status === 'completed' ? 'bg-emerald/10 border-emerald/30 text-emerald' :
                  s.status === 'running'   ? 'bg-accent-glow border-accent/40 text-accent-bright shadow-glow-sm' :
                  s.status === 'failed'    ? 'bg-rose-dim border-rose/30 text-rose' :
                  'bg-raised border-border text-dim'
                )}>
                  {s.status === 'running' && (
                    <span className="absolute inset-0 rounded-lg border border-accent/40 animate-ping opacity-50" />
                  )}
                  {STAGE_ICONS[s.stage]}
                </div>
                {!compact && (
                  <div className="mt-1.5 text-center">
                    <div className="text-2xs font-mono text-mid whitespace-nowrap">{STAGE_LABELS[s.stage]}</div>
                    {s.status === 'running' && s.detail && (
                      <div className="text-2xs text-subtle max-w-[80px] truncate">{s.detail}</div>
                    )}
                    {s.duration_ms && (
                      <div className="text-2xs font-mono text-dim">{s.duration_ms}ms</div>
                    )}
                  </div>
                )}
              </div>

              {/* Connector */}
              {i < stages.length - 1 && (
                <div className="flex-1 mx-0.5 relative">
                  <div className={cn(
                    'h-px transition-all duration-500',
                    s.status === 'completed' ? 'bg-emerald/40' :
                    s.status === 'running'   ? 'bg-gradient-to-r from-accent/40 to-border' :
                    'bg-border'
                  )} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
