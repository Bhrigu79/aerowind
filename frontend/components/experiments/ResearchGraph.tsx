'use client'

import { useEffect, useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/Badge'
import { getResearchGraph } from '@/lib/api/experiments'
import type { ResearchGraphData, GraphNode } from '@/lib/types'
import { FlaskConical, GitBranch, XCircle, CheckCircle, Target, Loader2, Info } from 'lucide-react'

export function ResearchGraph({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ResearchGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)

  useEffect(() => {
    getResearchGraph(projectId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [projectId])

  const { layout, width, height } = useMemo(() => {
    if (!data) return { layout: [], width: 0, height: 0 }

    // Compute grid layout
    const ySpacing = 160
    const xSpacing = 350
    const layout = new Map<string, { x: number, y: number, node: GraphNode }>()

    // Find root
    const root = data.nodes.find(n => n.id === 'root')
    if (root) layout.set('root', { x: 0, y: 0, node: root })

    // Build adjacency list for children
    const childrenMap = new Map<string, string[]>()
    data.edges.forEach(e => {
      const children = childrenMap.get(e.source) || []
      children.push(e.target)
      childrenMap.set(e.source, children)
    })

    let maxY = 0
    let maxX = 0
    let minX = 0

    // Assign coordinates
    const assignCoords = (nodeId: string, depth: number, currentX: number) => {
      maxY = Math.max(maxY, depth)

      const children = childrenMap.get(nodeId) || []

      // Sort children: retained first (stays on same X), rejected branch out
      const sortedChildren = children.map(cId => data.nodes.find(n => n.id === cId)!)
        .filter(Boolean)
        .sort((a, b) => {
          const aRet = a.data.decision === 'RETAIN' || a.id === data.current_best
          const bRet = b.data.decision === 'RETAIN' || b.id === data.current_best
          if (aRet && !bRet) return -1
          if (!aRet && bRet) return 1
          return 0
        })

      let nextX = currentX
      sortedChildren.forEach((child, i) => {
        let childX = currentX
        if (i > 0) { // Branch off
          childX = currentX + (i % 2 === 0 ? -1 : 1) * Math.ceil(i/2)
        }

        layout.set(child.id, { x: childX, y: depth + 1, node: child })
        maxX = Math.max(maxX, childX)
        minX = Math.min(minX, childX)

        assignCoords(child.id, depth + 1, childX)
      })
    }

    assignCoords('root', 0, 0)

    const layoutArr = Array.from(layout.values())
    const totalW = (maxX - minX + 2) * xSpacing
    const totalH = (maxY + 1) * ySpacing + 100

    return {
      layout: layoutArr.map(pos => ({
        ...pos,
        px: (pos.x - minX + 0.5) * xSpacing,
        py: pos.y * ySpacing + 50
      })),
      width: totalW,
      height: totalH
    }
  }, [data])

  if (loading) {
    return <div className="p-12 text-center text-dim flex items-center justify-center gap-3">
      <Loader2 className="w-5 h-5 animate-spin" /> Loading Research Graph...
    </div>
  }

  if (!data || data.nodes.length === 0) {
    return <div className="p-8 text-dim text-sm">No research data available for this project.</div>
  }

  return (
    <div className="flex bg-void rounded-xl border border-border overflow-hidden h-[600px]">
      <div className="flex-1 relative overflow-auto bg-[url('/grid.svg')] bg-center custom-scrollbar">
        <div style={{ width, height, position: 'relative' }}>
          {/* Edges */}
          <svg className="absolute inset-0 pointer-events-none" width={width} height={height}>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#333333" />
              </marker>
              <marker id="arrow-active" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#66bb6a" />
              </marker>
            </defs>
            {data.edges.map(edge => {
              const source = layout.find(l => l.node.id === edge.source)
              const target = layout.find(l => l.node.id === edge.target)
              if (!source || !target) return null

              const isRetainedPath = target.node.data.decision === 'RETAIN' || target.node.id === data.current_best
              const pathStr = `M ${source.px} ${source.py + 40} C ${source.px} ${source.py + 100}, ${target.px} ${target.py - 60}, ${target.px} ${target.py - 35}`

              return (
                <path
                  key={edge.id}
                  d={pathStr}
                  fill="none"
                  stroke={isRetainedPath ? "#66bb6a" : "#333333"}
                  strokeWidth={isRetainedPath ? 2 : 1.5}
                  strokeDasharray={isRetainedPath ? "none" : "4 4"}
                  markerEnd={isRetainedPath ? "url(#arrow-active)" : "url(#arrow)"}
                />
              )
            })}
          </svg>

          {/* Nodes */}
          {layout.map(({ node, px, py }) => {
            const isSelected = selectedNode?.id === node.id
            const isBest = node.id === data.current_best
            const isRejected = node.data.decision === 'REJECT'

            let bgClass = "bg-surface border-border hover:border-accent/50"
            if (isBest) bgClass = "bg-green-900/10 border-green-500/50"
            if (isRejected) bgClass = "bg-red-900/5 border-red-900/30 opacity-75"
            if (isSelected) bgClass += " ring-2 ring-accent"

            return (
              <motion.div
                key={node.id}
                className={`absolute w-[280px] -ml-[140px] -mt-[35px] rounded-xl border p-4 cursor-pointer transition-all ${bgClass}`}
                style={{ left: px, top: py }}
                onClick={() => setSelectedNode(node)}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {node.type === 'objective' ? <Target className="w-4 h-4 text-accent" /> :
                     isBest ? <CheckCircle className="w-4 h-4 text-green-400" /> :
                     isRejected ? <XCircle className="w-4 h-4 text-red-400" /> :
                     <FlaskConical className="w-4 h-4 text-dim" />}
                    <h3 className="text-sm font-medium text-bright truncate max-w-[180px]" title={node.data.title}>
                      {node.data.title}
                    </h3>
                  </div>
                  {isBest && <Badge variant="success">BEST</Badge>}
                </div>
                {node.type === 'objective' ? (
                  <p className="text-xs text-subtle line-clamp-2">{node.data.objective}</p>
                ) : (
                  <div>
                    <div className="flex items-center gap-2 mt-1 mb-2">
                       <Badge variant={node.data.state === 'running' ? 'warning' : 'default'} pulse={node.data.state === 'running'}>
                         {node.data.state?.toUpperCase()}
                       </Badge>
                       {isRejected && <Badge variant="error">REJECTED</Badge>}
                    </div>
                    {node.data.hypothesis && (
                      <p className="text-xs text-subtle line-clamp-2" title={node.data.hypothesis}>
                        {node.data.hypothesis}
                      </p>
                    )}
                  </div>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>

      {/* Side Panel */}
      <div className="w-[380px] border-l border-border bg-surface/50 p-6 flex flex-col gap-6 overflow-y-auto">
        {selectedNode ? (
          <NodeDetails node={selectedNode} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-dim text-center">
            <GitBranch className="w-8 h-8 mb-4 opacity-50" />
            <p className="text-sm">Select a node in the research graph to view details and reasoning.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function NodeDetails({ node }: { node: GraphNode }) {
  const d = node.data
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-accent mb-2">
          {node.type === 'objective' ? <Target className="w-5 h-5" /> : <FlaskConical className="w-5 h-5" />}
          <h2 className="text-lg font-semibold text-bright">{d.title}</h2>
        </div>
        {d.state && <Badge variant="default">{d.state.toUpperCase()}</Badge>}
        {d.decision && <Badge variant={d.decision === 'RETAIN' ? 'success' : d.decision === 'REJECT' ? 'error' : 'warning'} className="ml-2">{d.decision}</Badge>}
      </div>

      {node.type === 'objective' && d.objective && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-subtle uppercase tracking-wider">Objective</h4>
          <p className="text-sm text-dim bg-void p-3 rounded border border-border">{d.objective}</p>
        </div>
      )}

      {d.strategy_reason && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-accent uppercase tracking-wider flex items-center gap-1">
             <Info className="w-3 h-3"/> Research Strategy Engine
          </h4>
          <div className="text-sm text-dim bg-accent/5 p-3 rounded border border-accent/20">
             <div className="mb-2"><strong>Target Gap:</strong> {d.strategy_reason.target_constraint} (Gap: {(d.strategy_reason.gap * 100).toFixed(1)}%)</div>
             <div className="mb-2"><strong>Focus Dimension:</strong> {d.strategy_reason.selected_dimension}</div>
             <div className="text-xs text-subtle">{d.strategy_reason.reason}</div>
          </div>
        </div>
      )}

      {d.hypothesis && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-subtle uppercase tracking-wider">Hypothesis</h4>
          <p className="text-sm text-dim bg-void p-3 rounded border border-border">{d.hypothesis}</p>
        </div>
      )}

      {d.error_message && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-red-400 uppercase tracking-wider">Error / Rejection Reason</h4>
          <p className="text-sm text-red-300 bg-red-950/30 p-3 rounded border border-red-900/50 font-mono text-xs overflow-x-auto">
            {d.error_message}
          </p>
        </div>
      )}

      {d.candidate_metrics && (
        <div className="space-y-2">
           <h4 className="text-xs font-semibold text-subtle uppercase tracking-wider">Resulting Metrics</h4>
           <div className="grid grid-cols-2 gap-2">
              {Object.entries(d.candidate_metrics).filter(([k,v]) => typeof v === 'number').map(([k, v]) => (
                <div key={k} className="bg-void border border-border p-2 rounded">
                  <div className="text-[10px] text-subtle uppercase truncate" title={k}>{k.replace(/_/g, ' ')}</div>
                  <div className="text-sm font-medium text-bright">{typeof v === 'number' && v < 1 ? v.toFixed(4) : v}</div>
                </div>
              ))}
           </div>
        </div>
      )}
    </div>
  )
}
