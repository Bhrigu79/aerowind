'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createProject } from '@/lib/api/projects'
import { createResearchSession, runSessionIteration } from '@/lib/api/research'

export default function NewProjectPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    name: '',
    objective: '',
    target_system_description: '',
    quality_threshold: '90',
    latency_threshold: '2000',
    cost_threshold: '0.05',
    runner_type: 'synthetic'
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const p = await createProject({
        name: form.name,
        objective: form.objective,
        description: "Created from Web UI",
        target_system_description: form.target_system_description,
        constraints: [
          { metric: 'quality_score', operator: '>=', value: parseFloat(form.quality_threshold), unit: '%' },
          { metric: 'p95_latency_ms', operator: '<=', value: parseFloat(form.latency_threshold), unit: 'ms' },
          { metric: 'cost_per_request_usd', operator: '<=', value: parseFloat(form.cost_threshold), unit: '$' }
        ]
      })

      const sessionData = await createResearchSession(p.id, { max_iterations: 1, max_experiments: 2 });

      // Fire and forget the iteration (or await it if you want the user to wait)
      // Since it could take 5-10s for the synthetic run, we fire it off.
      runSessionIteration(sessionData.session_id, form.runner_type).catch(console.error)

      router.push('/dashboard')
    } catch (err) {
      console.error(err)
      alert("Failed to start research")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen">
      <div className="border-b border-border px-8 py-4 bg-surface/60 sticky top-0 z-30 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-dim hover:text-bright transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7"/>
            </svg>
          </Link>
          <div className="w-px h-4 bg-border" />
          <h1 className="text-sm font-semibold text-white">Create New Project</h1>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-8 py-10">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-panel border border-border rounded-xl p-6 space-y-5">
            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Project Name</label>
              <input type="text" required value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" placeholder="e.g. Customer Support Agent v2" />
            </div>

            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Objective</label>
              <textarea required value={form.objective} onChange={e => setForm({...form, objective: e.target.value})} rows={2} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" placeholder="Improve this agent so that quality stays above 92%..." />
            </div>

            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Target System Description</label>
              <textarea required value={form.target_system_description} onChange={e => setForm({...form, target_system_description: e.target.value})} rows={3} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" placeholder="A single prompt GPT-4o agent using LangChain..." />
            </div>
          </div>

          <div className="bg-panel border border-border rounded-xl p-6">
            <h3 className="text-sm font-medium text-white mb-4">Measurable Constraints</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Quality ≥ (%)</label>
                <input type="number" required value={form.quality_threshold} onChange={e => setForm({...form, quality_threshold: e.target.value})} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Latency ≤ (ms)</label>
                <input type="number" required value={form.latency_threshold} onChange={e => setForm({...form, latency_threshold: e.target.value})} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Cost/Req ≤ ($)</label>
                <input type="number" step="0.001" required value={form.cost_threshold} onChange={e => setForm({...form, cost_threshold: e.target.value})} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm" />
              </div>
            </div>
          </div>

          <div className="bg-panel border border-border rounded-xl p-6">
            <h3 className="text-sm font-medium text-white mb-4">Execution Engine</h3>
            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">Runner Type</label>
              <select value={form.runner_type} onChange={e => setForm({...form, runner_type: e.target.value})} className="w-full bg-raised border border-border rounded-lg px-4 py-2.5 text-bright focus:outline-none focus:border-accent/40 font-mono text-sm">
                <option value="synthetic">Synthetic (Simulation)</option>
                <option value="real_ai">Real AI Benchmark (Nebius / NVIDIA Nemotron)</option>
              </select>
              <p className="mt-2 text-xs text-dim font-mono">
                {form.runner_type === 'synthetic'
                  ? 'Simulates model behavior deterministically. Safe and fast.'
                  : 'Executes actual model requests via Nebius. Requires configured API credentials.'}
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Link href="/dashboard" className="px-5 py-2.5 border border-border text-mid rounded-xl text-sm hover:border-accent/30 hover:text-bright transition-all">Cancel</Link>
            <button type="submit" disabled={loading} className="px-5 py-2.5 bg-accent text-white rounded-xl text-sm font-semibold hover:bg-accent-bright transition-all shadow-glow-sm disabled:opacity-50">
              {loading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
