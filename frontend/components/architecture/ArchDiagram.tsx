'use client'
import { cn, PROVIDER_COLORS } from '@/lib/utils'
import type { SystemArchitecture, ArchNode } from '@/lib/types'

interface ArchDiagramProps {
  architecture: SystemArchitecture
  label?: string
  variant?: 'current' | 'baseline' | 'candidate'
  className?: string
}

const NODE_SHAPES: Record<ArchNode['type'], string> = {
  user:      'rounded-full',
  router:    'rounded-lg',
  model:     'rounded-xl',
  tool:      'rounded-lg',
  evaluator: 'rounded-lg',
  cache:     'rounded-md',
}

const NODE_STYLES: Record<ArchNode['type'], string> = {
  user:      'bg-accent-glow border-accent/30 text-accent-bright',
  router:    'bg-raised border-border text-bright',
  model:     'bg-raised border-border text-bright',
  tool:      'bg-raised border-border text-mid',
  evaluator: 'bg-raised border-border text-mid',
  cache:     'bg-amber-dim border-amber/20 text-amber',
}

const NODE_ICONS: Record<ArchNode['type'], string> = {
  user:      '◎',
  router:    '⇌',
  model:     '◈',
  tool:      '⚙',
  evaluator: '⊛',
  cache:     '◫',
}

// Simplified linear layout — renders nodes in topological order
function layoutNodes(arch: SystemArchitecture): Array<{ node: ArchNode; level: number }> {
  const levels: Record<string, number> = {}
  const visited = new Set<string>()

  function visit(nodeId: string, level: number) {
    if (visited.has(nodeId)) return
    visited.add(nodeId)
    levels[nodeId] = Math.max(levels[nodeId] ?? 0, level)
    const outgoing = arch.edges.filter(e => e.from === nodeId).map(e => e.to)
    outgoing.forEach(nId => visit(nId, level + 1))
  }

  // Find roots (no incoming edges)
  const hasIncoming = new Set(arch.edges.map(e => e.to))
  const roots = arch.nodes.filter(n => !hasIncoming.has(n.id))
  roots.forEach(r => visit(r.id, 0))

  return arch.nodes.map(node => ({ node, level: levels[node.id] ?? 0 }))
}

export function ArchDiagram({ architecture, label, variant = 'current', className }: ArchDiagramProps) {
  const layouted = layoutNodes(architecture)
  const maxLevel = Math.max(...layouted.map(n => n.level))

  // Group by level
  const byLevel: Record<number, ArchNode[]> = {}
  layouted.forEach(({ node, level }) => {
    if (!byLevel[level]) byLevel[level] = []
    byLevel[level].push(node)
  })

  const variantColors = {
    current:   'border-accent/20 bg-gradient-to-b from-panel to-raised',
    baseline:  'border-border bg-panel',
    candidate: 'border-emerald/20 bg-gradient-to-b from-panel to-raised',
  }

  return (
    <div className={cn(
      'border rounded-xl p-4 relative overflow-hidden',
      variantColors[variant],
      className
    )}>
      {label && (
        <div className="absolute top-3 left-3">
          <span className={cn(
            'text-2xs font-mono uppercase tracking-widest px-2 py-0.5 rounded border',
            variant === 'current'   ? 'text-accent-bright bg-accent-glow border-accent/20' :
            variant === 'baseline'  ? 'text-mid bg-muted/40 border-border' :
            'text-emerald bg-emerald-dim border-emerald/20'
          )}>
            {label}
          </span>
        </div>
      )}

      <div className="flex flex-col gap-3 pt-6">
        {Array.from({ length: maxLevel + 1 }, (_, level) => (
          <div key={level}>
            {/* Nodes at this level */}
            <div className={cn(
              'flex gap-2 justify-center',
              byLevel[level]?.length > 1 ? 'flex-wrap' : ''
            )}>
              {(byLevel[level] ?? []).map(node => {
                const providerColor = node.provider ? PROVIDER_COLORS[node.provider] : null

                return (
                  <div key={node.id}
                    className={cn(
                      'relative flex items-center gap-1.5 px-3 py-1.5 border text-xs font-mono transition-all',
                      NODE_SHAPES[node.type],
                      NODE_STYLES[node.type],
                    )}
                    style={providerColor ? {
                      borderColor: `${providerColor}40`,
                      backgroundColor: `${providerColor}10`,
                      color: providerColor,
                    } : {}}
                  >
                    <span>{NODE_ICONS[node.type]}</span>
                    <span>{node.label}</span>
                  </div>
                )
              })}
            </div>

            {/* Arrow to next level */}
            {level < maxLevel && (
              <div className="flex justify-center mt-1.5">
                <svg className="w-3 h-4 text-dim" fill="none" viewBox="0 0 12 16">
                  <path d="M6 0v12M1 8l5 6 5-6" stroke="currentColor" strokeWidth="1.5"
                    strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-2xs text-dim font-mono text-center mt-3 italic">{architecture.description}</p>
    </div>
  )
}

interface ArchEvolutionProps {
  before: SystemArchitecture
  after: SystemArchitecture
  className?: string
}

export function ArchEvolution({ before, after, className }: ArchEvolutionProps) {
  return (
    <div className={cn('bg-panel border border-border rounded-xl overflow-hidden', className)}>
      <div className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-medium text-bright">Architecture Evolution</h3>
        <p className="text-xs text-subtle mt-0.5">System design before and after optimization</p>
      </div>
      <div className="p-4 grid grid-cols-2 gap-3">
        <ArchDiagram architecture={before} label="Baseline" variant="baseline" />
        <ArchDiagram architecture={after} label="Current" variant="current" />
      </div>
    </div>
  )
}
