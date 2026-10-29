'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createExperiment } from '@/lib/api/experiments'
import { getProjects } from '@/lib/api/projects'
import { useEffect } from 'react'

const EXPERIMENT_TYPES = [
  { value: 'prompt_optimization', label: 'Prompt Optimization', icon: '◈', desc: 'Modify system prompts, few-shot examples, or instruction format.' },
  { value: 'model_swap', label: 'Model Swap', icon: '⇌', desc: 'Replace the primary model with a different provider or model size.' },
  { value: 'architecture_change', label: 'Architecture Change', icon: '⬡', desc: 'Change execution pattern: sequential ↔ parallel, routing, etc.' },
  { value: 'caching', label: 'Caching Strategy', icon: '◫', desc: 'Add or modify semantic or exact-match caching.' },
  { value: 'config_tuning', label: 'Config Tuning', icon: '⚙', desc: 'Adjust temperature, top_p, max_tokens, or other generation params.' },
  { value: 'system_redesign', label: 'System Redesign', icon: '✦', desc: 'Propose and test a fundamentally different architecture.' },
]

export default function NewExperimentPage() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState({
    type: '',
    name: '',
    description: '',
    candidate_description: '',
  })
  const [projectId, setProjectId] = useState<string>('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getProjects().then(ps => {
      if (ps.length > 0) setProjectId(ps[0].id)
    }).catch(console.error)
  }, [])

  async function handleLaunch() {
    if (!projectId) return;
    setLoading(true);
    try {
      const exp = await createExperiment({
        project_id: projectId,
        name: form.name,
        description: "Manually created",
        experiment_type: form.type,
        candidate_description: form.candidate_description,
        candidate_changes: {}
      })
      router.push(`/dashboard/experiments/${exp.id}`)
    } catch (e) {
      console.error(e)
      alert("Failed to create experiment")
    } finally {
      setLoading(false)
    }
  }

  const steps = ['Select Type', 'Describe Changes', 'Review']

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
          <h1 className="text-sm font-semibold text-white">New Experiment</h1>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-8 py-10">
        {/* Step indicator */}
        <div className="flex items-center gap-2 mb-10">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono border ${
                i < step  ? 'bg-emerald border-emerald/30 text-void' :
                i === step ? 'bg-accent-glow border-accent/30 text-accent-bright' :
                'bg-raised border-border text-dim'
              }`}>{i + 1}</div>
              <span className={`text-xs font-mono ${i === step ? 'text-bright' : 'text-dim'}`}>{s}</span>
              {i < steps.length - 1 && <div className="w-12 h-px bg-border ml-2" />}
            </div>
          ))}
        </div>

        {/* Step 0: Type selection */}
        {step === 0 && (
          <div className="space-y-4">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-white mb-1">What are you testing?</h2>
              <p className="text-subtle text-sm">Select the type of change you want to experiment with.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {EXPERIMENT_TYPES.map(t => (
                <button key={t.value}
                  onClick={() => { setForm(f => ({ ...f, type: t.value })); setStep(1) }}
                  className={`text-left p-4 rounded-xl border transition-all duration-200 hover:border-accent/40 hover:bg-raised ${
                    form.type === t.value ? 'border-accent/40 bg-accent-glow' : 'border-border bg-panel'
                  }`}>
                  <div className="text-2xl mb-2 text-accent-bright">{t.icon}</div>
                  <div className="text-sm font-medium text-bright mb-1">{t.label}</div>
                  <div className="text-xs text-subtle">{t.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 1: Describe */}
        {step === 1 && (
          <div className="space-y-5">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-white mb-1">Describe the experiment</h2>
              <p className="text-subtle text-sm">Be specific. AEROWIND will use this to design the test.</p>
            </div>

            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">
                Experiment Name
              </label>
              <input
                type="text"
                placeholder="e.g. CoT Prompting for Multi-Hop Queries"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full bg-raised border border-border rounded-xl px-4 py-3 text-bright placeholder:text-dim focus:outline-none focus:border-accent/40 font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-dim uppercase tracking-wider mb-2">
                Candidate Description
              </label>
              <textarea
                rows={4}
                placeholder="Describe the specific change being tested. E.g. 'Add explicit chain-of-thought reasoning steps to the system prompt for queries involving multiple logical steps.'"
                value={form.candidate_description}
                onChange={e => setForm(f => ({ ...f, candidate_description: e.target.value }))}
                className="w-full bg-raised border border-border rounded-xl px-4 py-3 text-bright placeholder:text-dim focus:outline-none focus:border-accent/40 font-mono text-sm resize-none"
              />
            </div>

            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep(0)} className="px-4 py-2.5 border border-border text-mid rounded-xl text-sm hover:border-accent/30 hover:text-bright transition-all">
                ← Back
              </button>
              <button
                onClick={() => form.name && form.candidate_description && setStep(2)}
                disabled={!form.name || !form.candidate_description}
                className="flex-1 px-4 py-2.5 bg-accent text-white rounded-xl text-sm font-medium hover:bg-accent-bright transition-all disabled:opacity-40 disabled:cursor-not-allowed">
                Continue →
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Review */}
        {step === 2 && (
          <div className="space-y-5">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-white mb-1">Review &amp; Launch</h2>
              <p className="text-subtle text-sm">AEROWIND will design, build, execute, measure, and analyze this experiment.</p>
            </div>

            <div className="bg-panel border border-border rounded-xl p-5 space-y-4">
              <div>
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-1">Type</div>
                <div className="text-sm text-bright">{EXPERIMENT_TYPES.find(t=>t.value===form.type)?.label}</div>
              </div>
              <div>
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-1">Name</div>
                <div className="text-sm text-bright">{form.name}</div>
              </div>
              <div>
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-1">Candidate</div>
                <div className="text-sm text-bright leading-relaxed">{form.candidate_description}</div>
              </div>
              <div>
                <div className="text-xs font-mono text-dim uppercase tracking-wider mb-1">Project</div>
                <div className="text-sm text-bright">Customer Support Agent v2</div>
              </div>
            </div>

            <div className="bg-amber-dim border border-amber/20 rounded-xl p-4">
              <div className="text-xs font-mono text-amber uppercase tracking-wider mb-1">Important</div>
              <p className="text-xs text-subtle">
                AEROWIND will run this experiment in an isolated sandbox.
                Measured results determine whether the change is adopted — no claims without evidence.
              </p>
            </div>

            <div className="flex gap-3 pt-2">
              <button onClick={() => setStep(1)} className="px-4 py-2.5 border border-border text-mid rounded-xl text-sm hover:border-accent/30 hover:text-bright transition-all">
                ← Back
              </button>
              <button
                onClick={handleLaunch}
                disabled={loading}
                className="flex-1 px-4 py-2.5 bg-accent text-white rounded-xl text-sm font-semibold hover:bg-accent-bright transition-all shadow-glow-sm disabled:opacity-50">
                {loading ? 'Launching...' : 'Launch Experiment →'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
