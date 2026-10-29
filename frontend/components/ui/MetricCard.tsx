import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string
  unit?: string
  delta?: string
  deltaGood?: boolean | null
  baseline?: string
  status?: 'normal' | 'warning' | 'success' | 'error'
  prominent?: boolean
  className?: string
  icon?: React.ReactNode
}

export function MetricCard({
  label, value, unit, delta, deltaGood, baseline,
  status = 'normal', prominent = false, className, icon
}: MetricCardProps) {
  const statusRing =
    status === 'success' ? 'border-emerald/20 shadow-glow-emerald' :
    status === 'error'   ? 'border-rose/20 shadow-glow-rose' :
    status === 'warning' ? 'border-amber/20' :
    'border-border'

  return (
    <div className={cn(
      'relative bg-panel border rounded-xl p-4 group transition-all duration-200 hover:border-accent/30',
      prominent ? 'bg-gradient-to-br from-panel to-raised' : '',
      statusRing,
      className
    )}>
      {/* Label */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-mono text-subtle uppercase tracking-widest">{label}</span>
        {icon && <span className="text-dim">{icon}</span>}
      </div>

      {/* Primary value */}
      <div className="flex items-baseline gap-1.5 mb-2">
        <span className={cn(
          'font-mono font-semibold leading-none',
          prominent ? 'text-3xl text-white' : 'text-2xl text-bright'
        )}>{value}</span>
        {unit && <span className="text-sm text-subtle font-mono">{unit}</span>}
      </div>

      {/* Baseline + delta */}
      {(baseline || delta) && (
        <div className="flex items-center gap-3 mt-1">
          {baseline && (
            <span className="text-xs font-mono text-dim">
              was <span className="text-subtle">{baseline}</span>
            </span>
          )}
          {delta && (
            <span className={cn(
              'text-xs font-mono font-medium',
              deltaGood === true  ? 'text-emerald' :
              deltaGood === false ? 'text-rose' :
              'text-mid'
            )}>
              {delta}
            </span>
          )}
        </div>
      )}

      {/* Status bar */}
      {status !== 'normal' && (
        <div className={cn(
          'absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl',
          status === 'success' ? 'bg-emerald/60' :
          status === 'error'   ? 'bg-rose/60' :
          status === 'warning' ? 'bg-amber/60' : ''
        )} />
      )}
    </div>
  )
}

// Compact inline metric
export function InlineMetric({ label, value, delta, deltaGood }: {
  label: string; value: string; delta?: string; deltaGood?: boolean | null
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border last:border-0">
      <span className="text-xs text-subtle font-mono">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-mono text-bright">{value}</span>
        {delta && (
          <span className={cn(
            'text-xs font-mono',
            deltaGood === true ? 'text-emerald' :
            deltaGood === false ? 'text-rose' : 'text-dim'
          )}>{delta}</span>
        )}
      </div>
    </div>
  )
}
