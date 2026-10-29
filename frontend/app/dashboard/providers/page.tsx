'use client'
import { useState, useEffect } from 'react'
import { ProviderPanel } from '@/components/providers/ProviderPanel'
import { getGatewayStatus } from '@/lib/api/providers'
import { PROVIDER_LABELS, PROVIDER_COLORS, formatMs } from '@/lib/utils'
import type { Provider, GatewayStatus } from '@/lib/types'

const PROVIDER_DETAIL: Record<Provider, { description: string; models: string[]; role: string }> = {
  nebius: {
    description: 'Nebius AI Cloud — primary inference provider with NVIDIA GPU infrastructure. Routes to Nemotron-70B for complex tasks and Nemotron-8B for fast/classification tasks.',
    models: ['nvidia/llama-3.1-nemotron-70b-instruct', 'meta-llama/Meta-Llama-3.1-8B-Instruct'],
    role: 'Primary + Reasoning',
  },
  openai: {
    description: 'OpenAI — secondary fallback. Used when Nebius is unavailable. GPT-4o-mini for cost-sensitive tasks.',
    models: ['gpt-4o', 'gpt-4o-mini'],
    role: 'Fallback',
  },
  anthropic: {
    description: 'Anthropic — tertiary fallback. Currently experiencing connectivity issues.',
    models: ['claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest'],
    role: 'Fallback',
  },
  gemini: {
    description: 'Google Gemini — quaternary fallback. Fast and cost-effective for simple tasks.',
    models: ['gemini-1.5-flash', 'gemini-1.5-pro'],
    role: 'Fallback',
  },
}

export default function ProvidersPage() {
  const [status, setStatus] = useState<GatewayStatus | null>(null)

  useEffect(() => {
    getGatewayStatus().then(setStatus).catch(console.error)
  }, [])

  if (!status) return <div className="p-8 text-dim">Loading gateway status... (Ensure backend is running)</div>

  return (
    <div className="min-h-screen">
      <div className="border-b border-border px-8 py-4 bg-surface/60 sticky top-0 z-30 backdrop-blur-sm">
        <div>
          <h1 className="text-sm font-semibold text-white">Model Providers</h1>
          <p className="text-xs text-subtle mt-0.5">
            Gateway status · {status.providers.filter(p=>p.is_healthy).length}/{status.providers.length} healthy ·
            {' '}{(status.total_tokens/1_000_000).toFixed(2)}M tokens · est. ${status.estimated_cost_usd.toFixed(4)}
          </p>
        </div>
      </div>

      <div className="px-8 py-6 space-y-5">
        {/* Gateway overview */}
        <div className="bg-panel border border-border rounded-xl p-5">
          <div className="text-xs font-mono text-dim uppercase tracking-wider mb-4">Model Gateway Architecture</div>
          <div className="flex items-center gap-3 text-xs font-mono">
            <div className="px-3 py-2 bg-accent-glow border border-accent/20 text-accent-bright rounded-lg">Agent Requests</div>
            <svg className="w-4 h-4 text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
            </svg>
            <div className="px-3 py-2 bg-amber-dim border border-amber/20 text-amber rounded-lg">ModelGateway</div>
            <svg className="w-4 h-4 text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
            </svg>
            <div className="px-3 py-2 bg-raised border border-border text-bright rounded-lg">Task Router</div>
            <svg className="w-4 h-4 text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
            </svg>
            <div className="flex gap-2">
              {status.providers.map(p => (
                <div key={p.provider}
                  className="px-2.5 py-2 rounded-lg border text-xs"
                  style={{ backgroundColor: `${PROVIDER_COLORS[p.provider]}15`, borderColor: `${PROVIDER_COLORS[p.provider]}30`, color: PROVIDER_COLORS[p.provider] }}>
                  {PROVIDER_LABELS[p.provider].split('/')[0].trim()}
                  <span className={`ml-1 w-1 h-1 rounded-full inline-block ${p.is_healthy ? 'bg-emerald' : 'bg-rose'}`} />
                </div>
              ))}
            </div>
          </div>
          <p className="text-xs text-dim mt-3">
            Agents never import provider SDKs directly. All calls go through the ModelGateway which handles routing, retries, fallback, health monitoring, and usage tracking.
          </p>
        </div>

        {/* Provider details */}
        <div className="grid grid-cols-2 gap-4">
          {status.providers.map(health => {
            const detail = PROVIDER_DETAIL[health.provider]
            const color = PROVIDER_COLORS[health.provider]
            return (
              <div key={health.provider}
                className="bg-panel border border-border rounded-xl overflow-hidden hover:border-accent/20 transition-colors">
                <div className="px-5 py-4 border-b border-border"
                  style={{ borderBottomColor: `${color}20` }}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold"
                        style={{ backgroundColor: `${color}20`, border: `1px solid ${color}40`, color }}>
                        {health.provider[0].toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-bright">{PROVIDER_LABELS[health.provider]}</div>
                        <div className="text-xs text-dim">{detail.role}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${health.is_healthy ? 'bg-emerald animate-pulse-slow' : 'bg-rose'}`} />
                      <span className={`text-xs font-mono ${health.is_healthy ? 'text-emerald' : 'text-rose'}`}>
                        {health.is_healthy ? 'HEALTHY' : 'ERROR'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  <p className="text-xs text-subtle leading-relaxed">{detail.description}</p>

                  <div className="space-y-1.5">
                    {detail.models.map(m => (
                      <div key={m} className="text-xs font-mono text-dim bg-raised/50 px-2 py-1 rounded border border-border truncate">
                        {m}
                      </div>
                    ))}
                  </div>

                  <div className="grid grid-cols-3 gap-2 pt-1">
                    <div className="text-center">
                      <div className="text-sm font-mono font-semibold text-bright">
                        {health.avg_latency_ms ? formatMs(health.avg_latency_ms) : '—'}
                      </div>
                      <div className="text-2xs text-dim">avg latency</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-sm font-mono font-semibold ${health.error_rate > 0.1 ? 'text-rose' : health.error_rate > 0 ? 'text-amber' : 'text-emerald'}`}>
                        {(health.error_rate * 100).toFixed(0)}%
                      </div>
                      <div className="text-2xs text-dim">error rate</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm font-mono font-semibold text-bright">{health.consecutive_failures}</div>
                      <div className="text-2xs text-dim">failures</div>
                    </div>
                  </div>

                  {health.message && (
                    <div className="text-xs font-mono text-rose bg-rose-dim px-2 py-1 rounded border border-rose/20">
                      {health.message}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Gateway stats */}
        <div className="bg-panel border border-border rounded-xl p-5">
          <div className="text-xs font-mono text-dim uppercase tracking-wider mb-4">Gateway Usage Statistics</div>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Total Requests', value: status.total_requests.toLocaleString() },
              { label: 'Total Tokens', value: `${(status.total_tokens/1_000_000).toFixed(2)}M` },
              { label: 'Est. Cost', value: `$${status.estimated_cost_usd.toFixed(4)}` },
              { label: 'Default Provider', value: PROVIDER_LABELS[status.default_provider].split('/')[0] },
            ].map(({ label, value }) => (
              <div key={label} className="text-center py-3 border border-border rounded-lg">
                <div className="text-xl font-mono font-bold text-white">{value}</div>
                <div className="text-xs text-dim mt-1">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
