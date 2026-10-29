'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { getEvidence } from '@/lib/api/evidence'

export default function EvidencePage() {
  const [evidence, setEvidence] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getEvidence()
      .then(data => {
        setEvidence(data)
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setError("Failed to load evidence")
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen p-8 text-dim flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-5 h-5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="text-sm font-mono uppercase tracking-widest">Loading Evidence...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return <div className="min-h-screen p-8 text-rose font-mono">{error}</div>
  }

  return (
    <div className="min-h-screen">
      <div className="border-b border-border px-8 py-4 bg-surface/60 sticky top-0 z-30 backdrop-blur-sm">
        <div>
          <h1 className="text-sm font-semibold text-white">Evidence Log</h1>
          <p className="text-xs text-subtle mt-0.5">
            Every conclusion is backed by measured data. No unsupported claims.
          </p>
        </div>
      </div>

      <div className="px-8 py-6 space-y-5">
        {evidence.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center border border-dashed border-border rounded-xl bg-panel">
            <div className="w-12 h-12 rounded-xl bg-surface/50 border border-border flex items-center justify-center mb-4 text-dim">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-sm font-medium text-bright mb-2">No evidence yet</h3>
            <p className="text-xs text-subtle max-w-sm mb-6">
              Evidence artifacts (logs, traces, and metrics) will appear here automatically once experiments are executed by the agents.
            </p>
            <Link href="/dashboard/experiments" className="px-5 py-2.5 bg-accent/15 border border-accent/30 text-accent-bright rounded-xl text-sm font-semibold hover:bg-accent/25 transition-all">
              View Experiments
            </Link>
          </div>
        ) : (
          <div className="text-sm text-dim">
            Evidence data is present but rendering is not yet implemented for real data schemas.
          </div>
        )}
      </div>
    </div>
  )
}
