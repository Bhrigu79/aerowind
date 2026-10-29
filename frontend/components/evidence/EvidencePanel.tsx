'use client'
import { cn } from '@/lib/utils'
import type { Experiment } from '@/lib/types'

interface EvidencePanelProps {
  experiments: Experiment[]
  className?: string
}

interface EvidenceItem {
  claim: string
  evidence: {
    metric: string
    baseline: string
    candidate: string
    sample_size: number
    quality_change?: string
  }
  conclusion: 'Supported' | 'Rejected' | 'Inconclusive'
  experiment_name: string
  experiment_id: string
}

function buildEvidence(experiments: Experiment[]): EvidenceItem[] {
  return experiments
    .filter(e => e.status === 'completed' && e.conclusion)
    .map(exp => {
      const isConfirmed = exp.hypothesis_confirmed
      const conclusion: EvidenceItem['conclusion'] =
        isConfirmed === true  ? 'Supported' :
        isConfirmed === false ? 'Rejected' :
        'Inconclusive'

      // Build evidence items from metric changes
      const evidences: EvidenceItem[] = []

      if (exp.baseline_metrics && exp.candidate_metrics) {
        // P95 latency
        if (exp.candidate_metrics.p95_latency_ms != null && exp.baseline_metrics.p95_latency_ms != null) {
          const bMs = exp.baseline_metrics.p95_latency_ms
          const cMs = exp.candidate_metrics.p95_latency_ms
          const pct = (((cMs - bMs) / bMs) * 100).toFixed(1)
          evidences.push({
            claim: `${exp.name}: "${exp.candidate_description}"`,
            evidence: {
              metric: 'P95 Latency',
              baseline: `${(bMs / 1000).toFixed(2)}s`,
              candidate: `${(cMs / 1000).toFixed(2)}s (${pct}%)`,
              sample_size: exp.baseline_metrics.total_requests,
              quality_change: exp.candidate_metrics.quality_score != null && exp.baseline_metrics.quality_score != null
                ? `${(exp.candidate_metrics.quality_score - exp.baseline_metrics.quality_score).toFixed(1)}pp`
                : undefined,
            },
            conclusion,
            experiment_name: exp.name,
            experiment_id: exp.id,
          })
        }
      }

      return evidences
    })
    .flat()
    .slice(0, 6)
}

export function EvidencePanel({ experiments, className }: EvidencePanelProps) {
  const items = buildEvidence(experiments)

  return (
    <div className={cn('bg-panel border border-border rounded-xl overflow-hidden', className)}>
      <div className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-medium text-bright">Evidence Log</h3>
        <p className="text-xs text-subtle mt-0.5">Every conclusion is backed by measured data.</p>
      </div>

      {items.length === 0 ? (
        <div className="py-12 text-center px-5">
          <div className="text-2xl text-dim mb-2">◫</div>
          <p className="text-sm text-subtle">No evidence collected yet.</p>
          <p className="text-xs text-dim mt-1">Evidence appears after experiments complete.</p>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {items.map((item, i) => (
            <div key={i} className="px-5 py-4">
              {/* Claim */}
              <div className="mb-3">
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-1">Claim</div>
                <p className="text-sm text-bright">{item.claim}</p>
              </div>

              {/* Evidence */}
              <div className="mb-3 bg-raised/50 rounded-lg p-3 border border-border">
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-2">Evidence</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  <div className="text-xs">
                    <span className="text-dim">Metric: </span>
                    <span className="text-bright font-mono">{item.evidence.metric}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-dim">Sample n=</span>
                    <span className="text-bright font-mono">{item.evidence.sample_size}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-dim">Baseline: </span>
                    <span className="font-mono text-mid">{item.evidence.baseline}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-dim">Candidate: </span>
                    <span className={cn(
                      'font-mono',
                      item.conclusion === 'Supported' ? 'text-emerald' :
                      item.conclusion === 'Rejected'  ? 'text-rose' : 'text-mid'
                    )}>{item.evidence.candidate}</span>
                  </div>
                  {item.evidence.quality_change && (
                    <div className="text-xs col-span-2">
                      <span className="text-dim">Quality Δ: </span>
                      <span className={cn(
                        'font-mono',
                        item.evidence.quality_change.startsWith('-') ? 'text-rose' : 'text-emerald'
                      )}>{item.evidence.quality_change}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Conclusion */}
              <div className="flex items-center justify-between">
                <div className="text-xs font-mono text-dim uppercase tracking-wider">Conclusion</div>
                <span className={cn(
                  'text-xs font-mono font-semibold px-2 py-0.5 rounded border',
                  item.conclusion === 'Supported'   ? 'text-emerald bg-emerald-dim border-emerald/20' :
                  item.conclusion === 'Rejected'    ? 'text-rose bg-rose-dim border-rose/20' :
                  'text-mid bg-muted/40 border-border'
                )}>
                  {item.conclusion}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
