import { useEffect, type ReactNode } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'
import { Button } from './ui'

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirmer',
  cancelLabel = 'Annuler',
  tone = 'danger',
  loading = false,
  onConfirm,
  onClose,
}: {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  loading?: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, loading, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      onClick={() => !loading && onClose()}
    >
      <div
        className="panel w-full max-w-md p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <span
            className={clsx(
              'grid h-11 w-11 shrink-0 place-items-center border',
              tone === 'danger'
                ? 'border-danger-400/30 bg-danger-400/10 text-danger-400'
                : 'border-gold-400/30 bg-gold-400/10 text-gold-300',
            )}
          >
            <AlertTriangle size={20} />
          </span>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="grid h-8 w-8 place-items-center text-sand-500 transition-colors hover:text-cream-100 disabled:opacity-40"
            aria-label="Fermer"
          >
            <X size={17} />
          </button>
        </div>

        <h2
          id="confirm-title"
          className="mt-4 font-display text-3xl tracking-wide text-cream-50"
        >
          {title}
        </h2>
        <div className="mt-2 text-sm leading-relaxed text-sand-400">{description}</div>

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            loading={loading}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
