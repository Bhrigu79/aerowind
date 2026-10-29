import { Sidebar } from '@/components/layout/Sidebar'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Research Console — AEROWIND',
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-void flex">
      <Sidebar />
      <main className="flex-1 ml-[220px] min-h-screen">
        {children}
      </main>
    </div>
  )
}
