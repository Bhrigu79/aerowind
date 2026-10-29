/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Base surfaces
        void:    '#070709',
        surface: '#0d0d14',
        raised:  '#12121c',
        panel:   '#161622',
        border:  '#1e1e2e',
        muted:   '#2a2a3d',
        // Text
        dim:     '#4a4a6a',
        subtle:  '#6b6b8a',
        mid:     '#8888aa',
        bright:  '#c0c0d8',
        white:   '#e8e8f0',
        // Accent — violet / indigo
        accent:   '#7c6df0',
        'accent-bright': '#9d8ff5',
        'accent-dim':    '#4a3fa0',
        'accent-glow':   'rgba(124,109,240,0.15)',
        // Status
        emerald:  '#10b981',
        'emerald-dim': 'rgba(16,185,129,0.12)',
        amber:    '#f59e0b',
        'amber-dim':   'rgba(245,158,11,0.12)',
        rose:     '#f43f5e',
        'rose-dim':    'rgba(244,63,94,0.12)',
        sky:      '#38bdf8',
        'sky-dim':     'rgba(56,189,248,0.10)',
        // Provider colors
        nebius:   '#6366f1',
        openai:   '#10a37f',
        anthropic:'#cc785c',
        gemini:   '#4285f4',
      },
      fontFamily: {
        sans:  ['Inter', 'system-ui', 'sans-serif'],
        mono:  ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '1rem' }],
      },
      backgroundImage: {
        'gradient-radial':  'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic':   'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'noise':            "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E\")",
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'glow':        'glow 2s ease-in-out infinite alternate',
        'scan':        'scan 4s linear infinite',
        'flow':        'flow 3s ease-in-out infinite',
        'shimmer':     'shimmer 2s linear infinite',
        'fade-up':     'fade-up 0.5s ease-out forwards',
        'fade-in':     'fade-in 0.3s ease-out forwards',
        'slide-right': 'slide-right 0.6s ease-out forwards',
      },
      keyframes: {
        glow: {
          '0%':   { boxShadow: '0 0 20px rgba(124,109,240,0.2)' },
          '100%': { boxShadow: '0 0 40px rgba(124,109,240,0.5), 0 0 80px rgba(124,109,240,0.1)' },
        },
        scan: {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        flow: {
          '0%, 100%': { opacity: '0.4' },
          '50%':      { opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'fade-up': {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-right': {
          '0%':   { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      boxShadow: {
        'glow-accent': '0 0 30px rgba(124,109,240,0.3)',
        'glow-sm':     '0 0 15px rgba(124,109,240,0.2)',
        'glow-emerald':'0 0 20px rgba(16,185,129,0.3)',
        'glow-rose':   '0 0 20px rgba(244,63,94,0.3)',
        'panel':       '0 4px 24px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.04) inset',
        'float':       '0 8px 40px rgba(0,0,0,0.5)',
      },
    },
  },
  plugins: [],
}
