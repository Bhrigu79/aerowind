'use client'
import Link from 'next/link'
import { useState, useEffect } from 'react'

// Animated research pipeline demo
const PIPELINE_STEPS = [
  { label: 'OBJECTIVE', detail: '"Quality >= 0.90, P95 < 2s"', color: 'text-accent-bright', bg: 'bg-accent-glow border-accent/30' },
  { label: 'HYPOTHESIS', detail: 'Generating candidate configuration...', color: 'text-bright', bg: 'bg-raised border-border' },
  { label: 'EXPERIMENT', detail: 'Designing baseline vs candidate.', color: 'text-bright', bg: 'bg-raised border-border' },
  { label: 'EXECUTION', detail: 'Running deterministically via Gateway.', color: 'text-bright', bg: 'bg-raised border-border' },
  { label: 'MEASUREMENT', detail: '0.85 -> 0.93 | 2400ms -> 1800ms', color: 'text-emerald', bg: 'bg-emerald-dim border-emerald/20' },
  { label: 'DECISION', detail: 'RETAIN. Constraints satisfied.', color: 'text-emerald', bg: 'bg-emerald-dim border-emerald/20' },
]

function AnimatedPipeline() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const t = setInterval(() => {
      setActive(a => (a + 1) % PIPELINE_STEPS.length)
    }, 2000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex flex-col gap-2">
      {PIPELINE_STEPS.map((step, i) => (
        <div key={step.label}
          className={`flex items-center gap-4 px-4 py-3 rounded-lg border text-sm transition-all duration-700 ${
            i === active ? `${step.bg} ${step.color}` : 'bg-raised/30 border-border/50 text-dim'
          }`}>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
            i === active ? 'bg-current animate-pulse' : 'bg-muted'
          }`} />
          <span className="font-mono font-medium w-28">{step.label}</span>
          {i === active && (
            <span className="font-mono text-xs opacity-90 truncate ml-auto">{step.detail}</span>
          )}
        </div>
      ))}
    </div>
  )
}

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-void relative overflow-hidden flex flex-col font-sans">
      {/* Background grid/noise */}
      <div className="absolute inset-0 grid-overlay opacity-30" />
      <div className="absolute inset-0 gradient-mesh opacity-50" />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between px-10 py-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-indigo-600 to-violet-800 flex items-center justify-center border border-indigo-400/30">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-xl font-bold tracking-wider text-bright">AEROWIND</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-sm font-medium text-subtle hover:text-bright transition-colors">
            Command Center
          </Link>
          <a href="https://github.com/aerowind" target="_blank" rel="noreferrer" className="text-sm font-medium text-subtle hover:text-bright transition-colors">
            GitHub
          </a>
        </div>
      </nav>

      {/* Hero */}
      <div className="relative z-10 flex-1 flex items-center justify-center px-8 pb-20">
        <div className="max-w-6xl w-full grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">

          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent/10 border border-accent/20">
              <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
              <span className="text-xs font-mono text-accent-bright uppercase tracking-wider">Phase 8 Enabled</span>
            </div>

            <h1 className="text-5xl lg:text-7xl font-bold tracking-tight text-white leading-[1.1]">
              Autonomous AI System Evolution
            </h1>

            <p className="text-lg text-subtle max-w-xl leading-relaxed">
              Give an AI system a measurable objective. AEROWIND designs experiments, runs them, measures what actually happened, and learns what works.
            </p>

            <div className="flex flex-wrap items-center gap-4 pt-4">
              <Link href="/dashboard/projects/new" className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-lg transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)]">
                Start Research
              </Link>
              <Link href="/dashboard" className="px-6 py-3 bg-raised border border-border hover:border-accent/50 text-bright font-medium rounded-lg transition-all">
                View Live Experiment
              </Link>
            </div>

            <div className="pt-8 flex items-center gap-6">
              <div className="flex flex-col">
                <span className="text-2xl font-mono font-medium text-white">Deterministic</span>
                <span className="text-xs text-dim uppercase tracking-wider">Evaluation</span>
              </div>
              <div className="w-px h-10 bg-border" />
              <div className="flex flex-col">
                <span className="text-2xl font-mono font-medium text-white">NVIDIA</span>
                <span className="text-xs text-dim uppercase tracking-wider">Nemotron Ready</span>
              </div>
              <div className="w-px h-10 bg-border" />
              <div className="flex flex-col">
                <span className="text-2xl font-mono font-medium text-emerald-400">Objective</span>
                <span className="text-xs text-dim uppercase tracking-wider">Driven</span>
              </div>
            </div>
          </div>

          <div className="relative hidden lg:block">
            {/* Visual presentation of the loop */}
            <div className="absolute -inset-4 bg-gradient-to-tr from-indigo-500/10 to-violet-500/10 rounded-2xl blur-2xl -z-10" />
            <div className="bg-panel border border-border/50 rounded-xl p-8 shadow-2xl backdrop-blur-sm">
              <div className="flex items-center justify-between mb-8 pb-4 border-b border-border/50">
                <span className="text-sm font-mono text-subtle uppercase tracking-widest">Research Orchestrator</span>
                <span className="text-xs font-mono text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded border border-emerald-400/20">LIVE</span>
              </div>
              <AnimatedPipeline />
            </div>
          </div>

        </div>
      </div>
    </main>
  )
}
