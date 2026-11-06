import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Clapperboard } from 'lucide-react'
import clsx from 'clsx'

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="group flex items-center gap-3" aria-label="GuessTheFrame">
      <span className="grid h-9 w-9 place-items-center border border-gold-400/40 bg-gold-400/10 text-gold-300 transition-colors group-hover:border-gold-300/70">
        <Clapperboard size={18} strokeWidth={1.6} />
      </span>
      {!compact && (
        <span className="font-display text-[1.7rem] leading-none tracking-[0.16em] text-cream-100">
          GUESS<span className="text-gold-400">THE</span>FRAME
        </span>
      )}
    </Link>
  )
}

export function SectionTitle({
  eyebrow,
  title,
  description,
  children,
  className,
}: {
  eyebrow?: string
  title: string
  description?: string
  children?: ReactNode
  className?: string
}) {
  return (
    <div className={clsx('flex flex-col gap-3', className)}>
      {eyebrow && (
        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-gold-400">
          {eyebrow}
        </span>
      )}
      <h2 className="font-display text-4xl leading-none tracking-[0.04em] text-cream-50 sm:text-5xl">
        {title}
      </h2>
      {description && (
        <p className="max-w-2xl text-sm leading-relaxed text-sand-400">{description}</p>
      )}
      {children}
    </div>
  )
}
