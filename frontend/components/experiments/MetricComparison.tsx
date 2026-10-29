'use client'
import { cn, formatMs, formatPercent, formatCost } from '@/lib/utils'
import type { MetricSnapshot } from '@/lib/types'

interface MetricCompareProps {
  baseline?: MetricSnapshot
  candidate?: MetricSnapshot
  className?: string
}

const METRICS_CONFIG = [
  {
    key: 'quality_score' as keyof MetricSnapshot,
    label: 'Quality Score',
    format: (v: number) => formatPercent(v),
    higherIsBetter: true,
    constraint: 92,
    constraintOp: '≥',
  },
  {
    key: 'p95_latency_ms' as keyof MetricSnapshot,
    label: 'P95 Latency',
    format: (v: number) => formatMs(v),
    higherIsBetter: false,
    constraint: 2000,
    constraintOp: '≤',
    unit: 'ms',
  },
  {
    key: 'p50_latency_ms' as keyof MetricSnapshot,
    label: 'P50 Latency',
    format: (v: number) => formatMs(v),
    higherIsBetter: false,
  },
  {
    key: 'cost_per_request_usd' as keyof MetricSnapshot,
    label: 'Cost / Request',
    format: (v: number) => formatCost(v),
    higherIsBetter: false,
    constraint: 0.03,
    constraintOp: '≤',
  },
  {
    key: 'throughput_rps' as keyof MetricSnapshot,
    label: 'Throughput',
    format: (v: number) => `${v.toFixed(1)} rps`,
    higherIsBetter: true,
  },
  {
    key: 'error_rate' as keyof MetricSnapshot,
    label: 'Error Rate',
    format: (v: number) => formatPercent(v * 100, 2),
    higherIsBetter: false,
  },
]

function DeltaBar({ baseline, candidate, higherIsBetter }: {
  baseline: number; candidate: number; higherIsBetter: boolean
}) {
  const diff = ((candidate - baseline) / Math.abs(baseline)) * 100
  const isGood = higherIsBetter ? diff >= 0 : diff <= 0
  const width = Math.min(Math.abs(diff), 100)

  return (
    <div className="relative h-1.5 bg-muted rounded-full overflow-hidden w-full">
      <div
        className={cn(
          'absolute top-0 h-full rounded-full transition-all duration-700',
          isGood ? 'bg-emerald' : 'bg-rose',
          diff < 0 ? 'right-1/2' : 'left-1/2'
        )}
        style={{ width: `${width / 2}%` }}
      />
      <div className="absolute left-1/2 top-0 w-px h-full bg-border" />
    </div>
  )
}

export function MetricComparison({ baseline, candidate, className }: MetricCompareProps) {
  if (!baseline) {
    return (
      <div className={cn('bg-panel border border-border rounded-xl p-5', className)}>
        <p className="text-sm text-dim text-center py-4">No baseline metrics available</p>
      </div>
    )
  }

  return (
    <div className={cn('bg-panel border border-border rounded-xl overflow-hidden', className)}>
      {/* Header */}
      <div className="grid grid-cols-[1fr_1px_1fr_1px_1fr] px-5 py-3 border-b border-border bg-raised/50">
        <div className="text-xs font-mono text-dim uppercase tracking-wider">Metric</div>
        <div className="bg-border" />
        <div className="text-xs font-mono text-dim uppercase tracking-wider text-center">
          Baseline
        </div>
        <div className="bg-border" />
        <div className="text-xs font-mono text-dim uppercase tracking-wider text-center">
          {candidate ? 'Candidate' : 'Result'}
        </div>
      </div>

      {/* Rows */}
      {METRICS_CONFIG.map(({ key, label, format, higherIsBetter, constraint, constraintOp }) => {
        const bVal = baseline[key] as number | undefined
        const cVal = candidate?.[key] as number | undefined

        const hasData = bVal != null
        const hasDelta = hasData && cVal != null
        const diff = hasDelta ? ((cVal! - bVal!) / Math.abs(bVal!)) * 100 : 0
        const isGood = higherIsBetter ? diff >= 0 : diff <= 0
        const meetsConstraint = constraint != null && cVal != null
          ? higherIsBetter ? cVal >= constraint : cVal <= constraint
          : null

        return (
          <div key={key} className="border-b border-border last:border-0 hover:bg-raised/30 transition-colors">
            <div className="grid grid-cols-[1fr_1px_1fr_1px_1fr] px-5 py-2.5">
              {/* Label */}
              <div className="flex flex-col justify-center">
                <span className="text-xs text-bright">{label}</span>
                {constraint != null && (
                  <span className="text-2xs font-mono text-dim">constraint {constraintOp} {format(constraint)}</span>
                )}
              </div>
              <div className="bg-border" />

              {/* Baseline */}
              <div className="flex items-center justify-center">
                <span className="text-sm font-mono text-mid">
                  {bVal != null ? format(bVal) : '—'}
                </span>
              </div>
              <div className="bg-border" />

              {/* Candidate */}
              <div className="flex flex-col items-center justify-center gap-0.5">
                {cVal != null ? (
                  <>
                    <div className="flex items-center gap-1.5">
                      <span className={cn(
                        'text-sm font-mono font-medium',
                        meetsConstraint === true  ? 'text-emerald' :
                        meetsConstraint === false ? 'text-rose' :
                        isGood ? 'text-emerald' : 'text-rose'
                      )}>{format(cVal)}</span>
                      {hasDelta && (
                        <span className={cn(
                          'text-2xs font-mono',
                          isGood ? 'text-emerald/70' : 'text-rose/70'
                        )}>
                          {diff > 0 ? '+' : ''}{diff.toFixed(1)}%
                        </span>
                      )}
                    </div>
                    {hasDelta && (
                      <DeltaBar baseline={bVal!} candidate={cVal} higherIsBetter={higherIsBetter} />
                    )}
                  </>
                ) : (
                  <span className="text-sm font-mono text-dim animate-pulse">—</span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
