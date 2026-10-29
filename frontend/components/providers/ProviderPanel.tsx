'use client'
import { cn, PROVIDER_COLORS, PROVIDER_LABELS, formatMs } from '@/lib/utils'
import type { GatewayStatus, Provider, ProviderHealth } from '@/lib/types'

interface ProviderPanelProps {
  status: GatewayStatus
  className?: string
}

const PROVIDER_ICONS: Record<Provider, string> = {
  nebius:    'N',
  openai:    'O',
  anthropic: 'A',
  gemini:    'G',
}

const PROVIDER_MODELS: Record<Provider, string> = {
  nebius:    'Nemotron 70B / 8B',
  openai:    'GPT-4o / GPT-4o-mini',
  anthropic: 'Claude 3.5 Sonnet',
  gemini:    'Gemini 1.5 Flash',
}

const PROVIDER_ROLE: Record<Provider, string> = {
  nebius:    'Primary (routing)',
  openai:    'Fallback',
  anthropic: 'Fallback',
  gemini:    'Fallback',
}

function ProviderRow({ health, isPrimary }: { health: ProviderHealth; isPrimary: boolean }) {
  const color = PROVIDER_COLORS[health.provider]

  return (
    <div className={cn(
      'flex items-center gap-3 px-4 py-3 border-b border-border last:border-0 group hover:bg-raised/40 transition-colors',
      isPrimary ? 'bg-raised/20' : ''
    )}>
      {/* Icon */}
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
        style={{ backgroundColor: `${color}22`, border: `1px solid ${color}44` }}
      >
        <span style={{ color }}>{PROVIDER_ICONS[health.provider]}</span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-bright font-medium">{PROVIDER_LABELS[health.provider]}</span>
          {isPrimary && (
            <span className="text-2xs font-mono text-accent-bright bg-accent-glow border border-accent/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
              Primary
            </span>
          )}
        </div>
        <div className="text-xs text-dim font-mono">{PROVIDER_MODELS[health.provider]}</div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4">
        {health.avg_latency_ms && (
          <div className="text-right">
            <div className="text-xs font-mono text-bright">{formatMs(health.avg_latency_ms)}</div>
            <div className="text-2xs text-dim">avg latency</div>
          </div>
        )}

        {/* Error rate */}
        <div className="text-right">
          <div className={cn(
            'text-xs font-mono',
            health.error_rate > 0.1 ? 'text-rose' :
            health.error_rate > 0 ? 'text-amber' : 'text-emerald'
          )}>
            {(health.error_rate * 100).toFixed(0)}%
          </div>
          <div className="text-2xs text-dim">errors</div>
        </div>

        {/* Status */}
        <div className="flex items-center gap-1.5">
          <span className={cn(
            'w-2 h-2 rounded-full',
            health.is_healthy ? 'bg-emerald animate-pulse-slow' : 'bg-rose'
          )} />
          <span className={cn(
            'text-xs font-mono',
            health.is_healthy ? 'text-emerald' : 'text-rose'
          )}>
            {health.is_healthy ? 'OK' : 'ERR'}
          </span>
        </div>
      </div>

      {/* Explicit message block if error (like Credentials not configured) */}
      {!health.is_healthy && health.message && (
        <div className="absolute top-1 right-4 text-2xs text-rose/70 italic">
          {health.message}
        </div>
      )}
    </div>
  )
}

export function ProviderPanel({ status, className }: ProviderPanelProps) {
  const healthyCount = status.providers.filter(p => p.is_healthy).length
  const totalM = (status.total_tokens / 1_000_000).toFixed(2)

  return (
    <div className={cn('bg-panel border border-border rounded-xl overflow-hidden', className)}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-bright">Model Providers</h3>
            <p className="text-xs text-subtle mt-0.5">
              {healthyCount}/{status.providers.length} healthy · {totalM}M tokens used
            </p>
          </div>
          <div className="flex gap-1">
            {status.providers.map(p => (
              <span
                key={p.provider}
                className={cn('w-2 h-2 rounded-full', p.is_healthy ? 'bg-emerald' : 'bg-rose')}
                title={p.provider}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Provider list */}
      <div>
        {status.providers.map(health => (
          <ProviderRow
            key={health.provider}
            health={health}
            isPrimary={health.provider === status.default_provider}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 bg-raised/30 border-t border-border">
        <div className="flex items-center justify-between text-xs">
          <span className="text-dim font-mono">Total estimated cost</span>
          <span className="text-bright font-mono font-semibold">
            ${status.estimated_cost_usd.toFixed(4)}
          </span>
        </div>
      </div>
    </div>
  )
}
