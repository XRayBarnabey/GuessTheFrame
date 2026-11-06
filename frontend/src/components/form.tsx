import type { InputHTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'

export const inputClass =
  'h-11 w-full border border-cream-100/12 bg-ink-950/60 px-3.5 text-sm text-cream-100 outline-none transition-colors placeholder:text-sand-500/60 focus:border-gold-400/60 focus:bg-ink-950'

export const inputClassSm =
  'h-9 w-full border border-cream-100/12 bg-ink-950/60 px-3 text-sm text-cream-100 outline-none transition-colors placeholder:text-sand-500/60 focus:border-gold-400/60 focus:bg-ink-950'

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string
  hint?: ReactNode
  error?: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={clsx('flex flex-col gap-2', className)}>
      <span className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-sand-400">
        {label}
      </span>
      {children}
      {hint && !error && (
        <span className="text-[0.7rem] leading-relaxed text-sand-500">{hint}</span>
      )}
      {error && <span className="text-[0.7rem] text-danger-400">{error}</span>}
    </label>
  )
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(inputClass, className)} />
}

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 text-sm text-sand-400">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[#d9b76f]"
      />
      <span>{label}</span>
    </label>
  )
}

export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        'relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-40',
        checked
          ? 'border-gold-400/60 bg-gold-400/25'
          : 'border-cream-100/15 bg-ink-800',
      )}
    >
      <span
        className={clsx(
          'absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full transition-all',
          checked ? 'left-[1.45rem] bg-gold-300' : 'left-1 bg-sand-500',
        )}
      />
    </button>
  )
}
