'use client'

import { useState, useEffect, useCallback } from 'react'
import { getProjects } from '@/lib/api/projects'
import { getResearchGraph } from '@/lib/api/experiments'
import { runSessionIteration, createResearchSession } from '@/lib/api/research'
import { createProject } from '@/lib/api/projects'
import { ResearchGraph } from '@/components/experiments/ResearchGraph'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import Link from 'next/link'
import type { Project, GraphNode } from '@/lib/types'

export default function DashboardPage() {
  const [project, setProject] = useState<Project | null>(null)
  const [graph, setGraph] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [iterating, setIterating] = useState(false)

  const loadData = useCallback(async () => {
    try {
      let ps = await getProjects()
      if (ps.length === 0) {
        await createProject({
          name: "Customer Support AI Optimization",
          objective: "Optimize support answering system to maximize quality while maintaining strict latency and cost bounds.",
          constraints: [
            { metric: "quality_score", operator: ">=", value: 92.0, unit: "%" },
            { metric: "p95_latency_ms", operator: "<=", value: 2000.0, unit: "ms" },
            { metric: "cost_per_request_usd", operator: "<=", value: 0.03, unit: "USD" }
          ],
          target_system_description: "Customer Support AI"
        })
        ps = await getProjects()
      }
      if (ps.length > 0) {
        setProject(ps[0])
        const g = await getResearchGraph(ps[0].id)
        setGraph(g)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleStartResearch = async () => {
    if (!project) return
    setIterating(true)
    try {
      let sessionId = graph?.session_id
      if (!sessionId) {
        const res = await createResearchSession(project.id, { max_iterations: 5, max_experiments: 20 })
        sessionId = res.session_id
      }
      // For demo, we just trigger the iteration. runner_type can be selected, but we default to synthetic for safety,
      // or check if there's a way to configure it. We'll use 'synthetic' by default, or 'nebius' if the user had it configured (hard to know here).
      // The prompt says: "Existing simulation mode is allowed and encouraged for local demo purposes, but it MUST remain explicitly labeled SIMULATION."
      await runSessionIteration(sessionId, 'synthetic')
      await loadData()
    } catch (e) {
      console.error(e)
      alert("Iteration failed")
    } finally {
      setIterating(false)
    }
  }

  if (loading) return <div className="min-h-screen bg-void p-8 text-dim font-mono text-sm">INITIALIZING AEROWIND CORE...</div>

  if (!project) {
    return (
      <div className="min-h-screen bg-void flex items-center justify-center p-8">
        <div className="max-w-md text-center space-y-6">
          <div className="w-16 h-16 rounded-2xl bg-surface/50 border border-border flex items-center justify-center mx-auto mb-6 shadow-glow">
            <svg className="w-8 h-8 text-bright" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
          </div>
          <h1 className="text-xl font-medium text-bright">No Active Research Project</h1>
          <p className="text-sm text-subtle font-mono">
            Give AEROWIND measurable constraints. It researches the design space, runs experiments, and uses measured evidence to decide what survives.
          </p>
          <Link href="/dashboard/projects/new" className="inline-block mt-4 px-6 py-3 bg-accent text-white font-mono text-sm uppercase tracking-wider rounded-lg shadow-glow-sm hover:bg-accent-bright transition-all">
            Configure Initial Objective
          </Link>
        </div>
      </div>
    )
  }

  const nodes = graph?.nodes || []
  const objectiveNode = nodes.find((n: GraphNode) => n.type === 'objective')
  const experimentNodes = nodes.filter((n: GraphNode) => n.type === 'experiment')
  const latestExp = experimentNodes[experimentNodes.length - 1]

  const currentBestId = graph?.current_best
  const currentBestExp = experimentNodes.find((n: GraphNode) => n.id === currentBestId)

  // Status computation
  const isExhausted = latestExp?.data.state === 'search_space_exhausted' || latestExp?.data.error_message?.includes('EXHAUSTED')
  const allConstraintsMet = Object.values(graph?.current_gaps || {}).every((m: any) => m.passed === true) && experimentNodes.length > 0
  const isComplete = allConstraintsMet || isExhausted

  return (
    <div className="min-h-screen bg-void text-bright font-sans selection:bg-accent/30">
      {/* Header - Objective-First Experience */}
      <header className="border-b border-border bg-surface/80 backdrop-blur-md sticky top-0 z-40 px-8 py-5">
        <div className="flex items-start justify-between max-w-7xl mx-auto">
          <div>
            <div className="text-xs font-mono text-accent uppercase tracking-widest mb-2 font-bold flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              AEROWIND // AUTONOMOUS AI PERFORMANCE ENGINEER
            </div>
            <div className="flex items-center gap-4 mb-2">
              <h1 className="text-2xl font-medium tracking-tight text-white">{project.name}</h1>
              {allConstraintsMet ? (
                <Badge variant="success">RESEARCH COMPLETE · OBJECTIVE SATISFIED</Badge>
              ) : isExhausted ? (
                <Badge variant="error">RESEARCH COMPLETE · SEARCH SPACE EXHAUSTED</Badge>
              ) : (
                <Badge variant="accent" pulse={iterating}>ACTIVE RESEARCH</Badge>
              )}
            </div>
            <p className="text-sm text-subtle max-w-2xl">{project.objective}</p>
          </div>
          <div className="flex flex-col items-end gap-3">
            {!isComplete && (
              <button
                onClick={handleStartResearch}
                disabled={iterating}
                className="px-6 py-2.5 bg-accent text-white font-mono text-xs uppercase tracking-wider rounded-lg shadow-glow-sm hover:bg-accent-bright transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {iterating ? (
                  <><span className="w-2 h-2 rounded-full bg-white animate-ping" /> ITERATING...</>
                ) : (
                  <>START AUTONOMOUS RESEARCH</>
                )}
              </button>
            )}
            <div className="text-xs font-mono text-dim">
              "AI proposes. Evidence decides."
            </div>
          </div>
        </div>
      </header>

      <main className="p-8 max-w-7xl mx-auto space-y-8">

        {/* Objective Constraints Bar */}
        <section className="bg-panel border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center gap-6">
            <span className="text-xs font-mono text-dim uppercase tracking-widest">Constraints</span>
            <div className="flex gap-4 flex-wrap">
              {project.constraints.map((c, i) => {
                const metricGap = graph?.current_gaps?.[c.metric]
                const isPassed = metricGap?.passed
                return (
                  <div key={i} className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded border text-sm font-mono",
                    isPassed ? "border-emerald/30 bg-emerald-dim/20 text-emerald" :
                    metricGap ? "border-rose/30 bg-rose-dim/20 text-rose" : "border-border text-subtle"
                  )}>
                    <span>{isPassed ? '✓' : metricGap ? '✕' : '○'}</span>
                    <span>{c.metric.replace(/_/g, ' ')} {c.operator} {c.value}{c.unit ? ` ${c.unit}` : ''}</span>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {experimentNodes.length === 0 ? (
          <div className="py-24 text-center border border-dashed border-border rounded-xl">
            <p className="text-dim font-mono text-sm mb-4">No experiments run yet.</p>
            <p className="text-subtle text-sm">Click "Start Autonomous Research" to begin the optimization loop.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

            {/* Left Column: Latest Experiment (Execution View) */}
            <div className="lg:col-span-2 space-y-6">

              {isExhausted && (
                <div className="p-5 border border-rose/30 bg-rose-dim/10 rounded-xl">
                  <h3 className="text-rose font-mono text-sm uppercase tracking-wider mb-2">SEARCH SPACE EXHAUSTED</h3>
                  <p className="text-sm text-subtle">{latestExp?.data.error_message}</p>
                  <p className="text-sm text-subtle mt-2">No remaining configured dimension produced a satisfying candidate.</p>
                </div>
              )}

              {(!isExhausted && latestExp) && (
                <div className="bg-panel border border-border rounded-xl overflow-hidden shadow-sm">
                  <div className="border-b border-border px-6 py-4 flex items-center justify-between bg-surface/50">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-dim uppercase tracking-wider">Experiment {(experimentNodes.indexOf(latestExp) + 1).toString().padStart(2, '0')}</span>
                      <div className="w-1.5 h-1.5 rounded-full bg-border" />
                      <span className="text-sm font-medium">{latestExp.data.title}</span>
                    </div>
                    {/* Provenance Badge */}
                    <div className={cn(
                      "px-3 py-1 rounded text-xs font-mono uppercase tracking-widest border font-bold flex items-center gap-2",
                      latestExp.data.runner_type?.includes('SIMULATION')
                        ? "border-amber-500/50 text-amber-500 bg-amber-500/10"
                        : "border-nebius/40 text-nebius bg-nebius/10"
                    )}>
                      {latestExp.data.runner_type?.includes('SIMULATION') && <span>⚠️</span>}
                      {latestExp.data.runner_type}
                    </div>
                  </div>

                  <div className="p-6 space-y-8">

                    {/* Hypothesis */}
                    <div>
                      <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-3">Hypothesis</h3>
                      <p className="text-sm text-bright leading-relaxed bg-surface p-4 rounded-lg border border-border/50">
                        {latestExp.data.hypothesis || "No explicit hypothesis"}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      {/* What Changed */}
                      <div>
                        <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-3">What Changed</h3>
                        <div className="space-y-2">
                          {Object.entries(latestExp.data.what_changed || {}).length > 0 ? (
                            Object.entries(latestExp.data.what_changed || {}).map(([k, v]: [string, any]) => (
                              <div key={k} className="flex justify-between items-center text-sm font-mono bg-surface px-3 py-2 rounded border border-border/50">
                                <span className="text-subtle">{k}</span>
                                <span className="text-accent-bright">{String(v.to)}</span>
                              </div>
                            ))
                          ) : (
                            <div className="text-sm text-dim font-mono">No dimensions changed.</div>
                          )}
                        </div>
                      </div>

                      {/* Why (Strategy Reason) */}
                      <div>
                        <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-3">Strategy Reasoning</h3>
                        <div className="text-sm text-subtle leading-relaxed p-3 bg-surface rounded border border-border/50">
                          {latestExp.data.strategy_reason?.reason || "Autonomous selection."}
                        </div>
                      </div>
                    </div>

                    {/* Metric Result Card */}
                    {latestExp.data.state === 'completed' && (
                      <div className="pt-2 border-t border-border">
                        <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-4">Measured Results</h3>
                        <div className="grid gap-3">
                          {project.constraints.map((c, i) => {
                            const val = latestExp.data.candidate_metrics?.[c.metric]
                            const passed = val != null
                              ? (c.operator === '>=' ? val >= c.value : c.operator === '<=' ? val <= c.value : false)
                              : false
                            return (
                              <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-border bg-surface">
                                <span className="text-sm text-subtle font-medium">{c.metric.replace(/_/g, ' ')}</span>
                                <div className="flex items-center gap-4">
                                  <span className="text-sm font-mono text-bright">
                                    {val != null ? (typeof val === 'number' && val % 1 !== 0 ? val.toFixed(3) : val) : '—'}
                                  </span>
                                  <span className={cn("w-6 h-6 flex items-center justify-center rounded-full text-xs font-bold", passed ? "bg-emerald/20 text-emerald" : "bg-rose/20 text-rose")}>
                                    {passed ? '✓' : '✕'}
                                  </span>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {/* Deterministic Decision Card */}
                    <div className="flex items-stretch gap-4 pt-4">
                      <div className={cn(
                        "flex-1 p-5 rounded-xl border",
                        latestExp.data.decision === 'RETAIN' ? "bg-emerald-dim/10 border-emerald/30" : "bg-rose-dim/10 border-rose/30"
                      )}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-mono text-dim uppercase tracking-wider">Decision</span>
                          <span className={cn("text-sm font-bold font-mono tracking-widest", latestExp.data.decision === 'RETAIN' ? "text-emerald" : "text-rose")}>
                            {latestExp.data.decision}
                          </span>
                        </div>
                        <p className="text-sm text-bright mb-4">
                          {latestExp.data.decision === 'RETAIN' ? "All required constraints satisfied." : "Candidate failed to satisfy required thresholds."}
                        </p>
                        <div className="flex items-center justify-between text-xs font-mono text-dim border-t border-border/50 pt-3">
                          <span>Source: CONSTRAINT ENGINE</span>
                          <span>LLM OVERRIDE: NOT ALLOWED</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Right Column: Reasoning & Current Best */}
            <div className="space-y-6">

              {/* Next Strategy */}
              {!isComplete && latestExp && latestExp.data.state === 'completed' && (
                <div className="bg-panel border border-border rounded-xl p-5 shadow-sm">
                  <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-4 flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    Next Strategy
                  </h3>
                  <div className="space-y-3 mb-4">
                    {latestExp.data.strategy_reason?.explored_dimensions?.map((d: string) => (
                      <div key={d} className="flex items-center gap-2 text-xs font-mono text-subtle">
                        <span className="text-emerald">✓</span> {d} explored
                      </div>
                    ))}
                    <div className="flex items-center gap-2 text-xs font-mono text-subtle">
                      <span className="text-emerald">✓</span> Previous configuration rejected
                    </div>
                  </div>

                  {latestExp.data.strategy_reason?.target_constraint !== 'general' && (
                    <div className="mb-4">
                      <div className="text-xs font-mono text-dim mb-1">Largest remaining constraint gap:</div>
                      <div className="text-sm font-mono text-rose uppercase">{latestExp.data.strategy_reason?.target_constraint?.replace(/_/g, ' ')}</div>
                    </div>
                  )}

                  <div className="mb-6">
                    <div className="text-xs font-mono text-dim mb-1">Next dimension to explore:</div>
                    <div className="text-sm font-mono text-accent-bright uppercase">{latestExp.data.strategy_reason?.selected_dimension || '—'}</div>
                  </div>

                  <div className="text-xs font-mono text-dim border-t border-border pt-4">
                    GENERATING NEXT HYPOTHESIS...
                  </div>
                </div>
              )}

              {/* Current Best */}
              {currentBestExp && (
                <div className="bg-surface border border-emerald/30 rounded-xl overflow-hidden shadow-glow-sm shadow-emerald/5">
                  <div className="bg-emerald-dim/20 px-5 py-3 border-b border-emerald/20 flex flex-col justify-center">
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-xs font-mono text-emerald uppercase tracking-widest">Current Best</h3>
                      <span className="text-2xs font-mono px-2 py-0.5 rounded bg-emerald/20 text-emerald">RETAINED</span>
                    </div>
                    <div className="text-[10px] font-mono text-emerald/70 leading-tight">
                      The best retained configuration under the current objective constraints/research policy.
                    </div>
                  </div>
                  <div className="p-5 space-y-4">
                    <div className="space-y-2">
                      {project.constraints.map((c, i) => {
                        const val = currentBestExp.data.candidate_metrics?.[c.metric]
                        return (
                          <div key={i} className="flex justify-between items-center text-sm font-mono">
                            <span className="text-subtle">{c.metric.replace(/_/g, ' ')}</span>
                            <span className="text-bright">{val != null ? (typeof val === 'number' && val % 1 !== 0 ? val.toFixed(3) : val) : '—'}</span>
                          </div>
                        )
                      })}
                    </div>

                    <div className="pt-4 border-t border-border/50">
                      <h4 className="text-xs font-mono text-dim uppercase tracking-wider mb-2">Configuration Summary</h4>
                      <div className="text-xs font-mono text-subtle space-y-1">
                        {Object.entries(graph?.current_best_config || {}).slice(0,4).map(([k,v]) => (
                          <div key={k} className="flex justify-between">
                            <span>{k}</span>
                            <span className="text-bright">{String(v)}</span>
                          </div>
                        ))}
                        {Object.keys(graph?.current_best_config || {}).length > 4 && (
                          <div className="text-dim italic mt-1">...and more</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {/* Search Space Atlas */}
              <div className="bg-panel border border-border rounded-xl p-5 shadow-sm mt-6">
                <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  Search Space Dimensions
                </h3>
                <div className="flex flex-wrap gap-2 text-xs font-mono">
                  {['model', 'temperature', 'max_tokens', 'prompt_strategy', 'few_shot_count', 'retrieval_enabled', 'chain_of_thought', 'pipeline_mode'].map(dim => (
                    <span key={dim} className="px-2 py-1 bg-surface border border-border/50 rounded text-subtle">
                      {dim}
                    </span>
                  ))}
                </div>
              </div>

              {/* Failure Knowledge Atlas */}
              <div className="bg-panel border border-border rounded-xl p-5 shadow-sm mt-6">
                <h3 className="text-xs font-mono text-rose uppercase tracking-wider mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose" />
                  Failure Knowledge
                </h3>
                <div className="space-y-4">
                  {experimentNodes.filter((e: any) => e.data.decision === 'REJECT').slice(-3).reverse().map((failExp: any) => (
                    <div key={failExp.id} className="border-b border-border/50 pb-3 last:border-0 last:pb-0">
                      <div className="text-xs font-mono text-subtle mb-1">
                        Rejected Config:
                      </div>
                      <div className="text-2xs font-mono text-dim mb-2 line-clamp-2">
                         {Object.entries(failExp.data.what_changed || {}).map(([k, v]: any) => `${k}=${v.to}`).join(', ')}
                      </div>
                      <div className="text-xs font-mono text-rose">
                        Reason: {failExp.data.error_message || "Failed constraint thresholds."}
                      </div>
                    </div>
                  ))}
                  {experimentNodes.filter((e: any) => e.data.decision === 'REJECT').length === 0 && (
                     <div className="text-xs font-mono text-dim">No failures recorded yet.</div>
                  )}
                </div>
              </div>

            </div>
          </div>
        )}

        {/* Research Graph */}
        {experimentNodes.length > 0 && (
          <section className="bg-panel border border-border rounded-xl p-5 mt-8 overflow-x-auto shadow-sm">
            <h3 className="text-xs font-mono text-dim uppercase tracking-wider mb-6">Research Lineage</h3>
            <div className="flex items-center gap-4 min-w-max pb-4">

              <div className="flex flex-col items-center justify-center w-24 flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-surface border border-border flex items-center justify-center text-xs font-mono mb-2">
                  START
                </div>
              </div>

              {experimentNodes.map((exp: GraphNode, i: number) => {
                const isRetained = exp.data.decision === 'RETAIN'
                const isRejected = exp.data.decision === 'REJECT'
                return (
                  <div key={exp.id} className="flex items-center">
                    <div className="w-8 h-px bg-border mx-2" />
                    <div className={cn(
                      "w-72 p-4 rounded-lg border flex flex-col gap-3 transition-all flex-shrink-0",
                      isRetained ? "bg-emerald-dim/10 border-emerald/40" :
                      isRejected ? "bg-surface border-border opacity-70" : "bg-panel border-accent/40 shadow-glow-sm"
                    )}>
                      <div className="flex justify-between items-center text-xs font-mono mb-1">
                        <span className="text-dim">EXP {String(i+1).padStart(2,'0')}</span>
                        <span className={cn(
                          "font-bold",
                          isRetained ? "text-emerald" : isRejected ? "text-rose" : "text-accent-bright"
                        )}>{exp.data.decision || exp.data.state}</span>
                      </div>

                      {/* Hypothesis & Strategy */}
                      <div className="space-y-2">
                        <div className="text-xs text-bright font-medium leading-tight">
                          {exp.data.title}
                        </div>
                        <div className="text-2xs font-mono text-subtle leading-tight line-clamp-2" title={exp.data.strategy_reason?.reason}>
                          <span className="text-dim">Why:</span> {exp.data.strategy_reason?.reason || "Autonomous selection"}
                        </div>
                        <div className="text-2xs font-mono text-subtle leading-tight line-clamp-2" title={exp.data.hypothesis}>
                          <span className="text-dim">Hyp:</span> {exp.data.hypothesis || "No explicit hypothesis"}
                        </div>
                      </div>

                      {/* What Changed & Metrics */}
                      <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/50">
                        <div>
                          <div className="text-[9px] font-mono text-dim uppercase mb-1">Changed</div>
                          <div className="text-2xs font-mono text-accent-bright line-clamp-2">
                            {Object.entries(exp.data.what_changed || {}).map(([k, v]) => `${k}=${String(v).substring(0, 10)}`).join(', ') || "None"}
                          </div>
                        </div>
                        <div>
                          <div className="text-[9px] font-mono text-dim uppercase mb-1">Metrics</div>
                          <div className="text-2xs font-mono space-y-0.5">
                            {Object.entries(exp.data.candidate_metrics || {}).slice(0, 3).map(([k, v]) => {
                               const shortK = k.split('_')[0]
                               const dispV = typeof v === 'number' && v % 1 !== 0 ? v.toFixed(2) : String(v)
                               return <div key={k} className="text-subtle truncate"><span className="text-dim">{shortK}:</span> {dispV}</div>
                            })}
                          </div>
                        </div>
                      </div>

                      {/* Provenance */}
                      <div className="text-[9px] font-mono text-dim tracking-widest uppercase border-t border-border/50 pt-2 mt-auto">
                        {exp.data.runner_type || "SIMULATION"}
                      </div>
                    </div>
                  </div>
                )
              })}

              {allConstraintsMet && (
                <div className="flex items-center">
                  <div className="w-8 h-px bg-emerald/40 mx-2" />
                  <div className="w-32 p-3 rounded-lg border border-emerald bg-emerald/10 flex flex-col items-center text-center shadow-glow-sm shadow-emerald/20">
                    <span className="text-emerald text-lg mb-1">✓</span>
                    <span className="text-xs font-mono text-emerald">OBJECTIVE SATISFIED</span>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

      </main>
    </div>
  )
}
