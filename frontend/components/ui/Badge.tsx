import { cn } from '@/lib/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'error' | 'accent' | 'info'
  size?: 'sm' | 'md'
  pulse?: boolean
  className?: string
}

const VARIANTS = {
  default:  'text-mid bg-muted/40 border-border',
  success:  'text-emerald bg-emerald-dim border-emerald/20',
  warning:  'text-amber bg-amber-dim border-amber/20',
  error:    'text-rose bg-rose-dim border-rose/20',
  accent:   'text-accent-bright bg-accent-glow border-accent/20',
  info:     'text-sky bg-sky-dim border-sky/20',
}

export function Badge({ children, variant = 'default', size = 'sm', pulse = false, className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 font-mono font-medium border rounded-md uppercase tracking-wider',
      size === 'sm' ? 'text-2xs px-1.5 py-0.5' : 'text-xs px-2 py-1',
      VARIANTS[variant],
      className
    )}>
      {pulse && (
        <span className={cn(
          'w-1.5 h-1.5 rounded-full flex-shrink-0',
          variant === 'success' ? 'bg-emerald animate-pulse-slow' :
          variant === 'warning' ? 'bg-amber animate-pulse-slow' :
          variant === 'error'   ? 'bg-rose animate-pulse-slow' :
          variant === 'accent'  ? 'bg-accent animate-pulse-slow' :
          variant === 'info'    ? 'bg-sky animate-pulse-slow' :
          'bg-mid animate-pulse-slow'
        )} />
      )}
      {children}
    </span>
  )
}
