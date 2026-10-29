import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AEROWIND — Autonomous AI System Evolution',
  description: 'Give AI an objective. AEROWIND experiments until the system gets there. Autonomous AI performance engineering backed by measured evidence.',
  keywords: ['AI optimization', 'autonomous experiments', 'AI engineering', 'model optimization'],
  openGraph: {
    title: 'AEROWIND — Autonomous AI System Evolution',
    description: 'Give AI an objective. AEROWIND experiments until the system gets there.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-void text-bright antialiased">
        {children}
      </body>
    </html>
  )
}
