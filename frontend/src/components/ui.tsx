import type { ButtonHTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'
import { LoaderCircle } from 'lucide-react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variants: Record<ButtonVariant, string> = {
  primary:
    'bg-gold-400 text-on-accent hover:bg-gold-300 active:bg-gold-500 disabled:bg-gold-400/30 disabled:text-on-accent/50',
  secondary:
    'border border-cream-100/15 bg-cream-100/[0.04] text-cream-100 hover:border-gold-400/50 hover:bg-gold-400/[0.06] disabled:opacity-40',
  ghost:
    'text-sand-400 hover:bg-cream-100/[0.05] hover:text-cream-100 disabled:opacity-40',
  danger:
    'border border-danger-400/35 bg-danger-400/10 text-danger-400 hover:bg-danger-400/20 disabled:opacity-40',
}

export function Button({
  variant = 'primary',
  loading = false,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  loading?: boolean
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={clsx(
        'inline-flex h-11 items-center justify-center gap-2 px-5 text-[0.72rem] font-semibold uppercase tracking-[0.18em] transition-all duration-200 disabled:cursor-not-allowed',
        variants[variant],
        className,
      )}
    >
      {loading && <LoaderCircle size={15} className="animate-spin" />}
      {children}
    </button>
  )
}

export function Card({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={clsx('panel rounded-sm', className)}>{children}</div>
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'gold' | 'success' | 'danger'
}) {
  const tones = {
    neutral: 'border-cream-100/12 bg-cream-100/[0.04] text-sand-400',
    gold: 'border-gold-400/30 bg-gold-400/10 text-gold-300',
    success: 'border-success-400/25 bg-success-400/10 text-success-400',
    danger: 'border-danger-400/30 bg-danger-400/10 text-danger-400',
  }
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 border px-2.5 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.18em]',
        tones[tone],
      )}
    >
      {children}
    </span>
  )
}

export function Spinner({ label = 'Chargement' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-sand-500">
      <LoaderCircle size={16} className="animate-spin text-gold-400" />
      {label}
    </span>
  )
}

export function PageLoader() {
  return (
    <div className="grid min-h-[55svh] place-items-center">
      <Spinner label="Chargement" />
    </div>
  )
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="border border-danger-400/30 bg-danger-400/[0.07] px-4 py-3 text-sm text-danger-400"
    >
      {message}
    </div>
  )
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="border border-gold-400/20 bg-gold-400/[0.05] px-4 py-3 text-sm leading-relaxed text-gold-300/90">
      {children}
    </div>
  )
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: ReactNode
  hint?: string
}) {
  return (
    <div className="border border-cream-100/[0.07] bg-ink-900/50 px-4 py-4">
      <div className="text-[0.62rem] font-semibold uppercase tracking-[0.2em] text-sand-500">
        {label}
      </div>
      <div className="mt-2 font-display text-3xl leading-none tracking-wide text-cream-50">
        {value}
      </div>
      {hint && <div className="mt-1 text-[0.7rem] text-sand-500">{hint}</div>}
    </div>
  )
}
