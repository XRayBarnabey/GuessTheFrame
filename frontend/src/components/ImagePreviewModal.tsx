import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import {
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Maximize2,
  RotateCcw,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

const MIN_ZOOM = 1
const MAX_ZOOM = 8

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function ImagePreviewModal({
  sources,
  index,
  onIndexChange,
  onClose,
  version = 0,
}: {
  sources: string[]
  index: number
  onIndexChange: (index: number) => void
  onClose: () => void
  version?: number
}) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{
    pointerX: number
    pointerY: number
    panX: number
    panY: number
  } | null>(null)

  const src = sources[index] ?? ''
  const srcWithVersion = `${src}${src.includes('?') ? '&' : '?'}v=${version}-preview`

  function clampPan(nextX: number, nextY: number, nextZoom: number) {
    const element = viewportRef.current
    if (!element) return { x: nextX, y: nextY }
    const maxX = (element.clientWidth * (nextZoom - 1)) / 2
    const maxY = (element.clientHeight * (nextZoom - 1)) / 2
    return {
      x: clamp(nextX, -maxX, maxX),
      y: clamp(nextY, -maxY, maxY),
    }
  }

  function resetView() {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  useEffect(() => {
    setLoaded(false)
    setFailed(false)
    resetView()
  }, [srcWithVersion])

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowLeft' && index > 0) onIndexChange(index - 1)
      if (event.key === 'ArrowRight' && index < sources.length - 1) {
        onIndexChange(index + 1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [index, onClose, onIndexChange, sources.length])

  // Native (non-passive) wheel listener so zooming never scrolls the page.
  useEffect(() => {
    const element = viewportRef.current
    if (!element) return
    function onWheel(event: WheelEvent) {
      event.preventDefault()
      const rect = element!.getBoundingClientRect()
      const pointerX = event.clientX - rect.left - rect.width / 2
      const pointerY = event.clientY - rect.top - rect.height / 2
      const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
      setZoom((current) => {
        const next = clamp(current * factor, MIN_ZOOM, MAX_ZOOM)
        if (next === current) return current
        setPan((previous) => {
          const ratio = next / current
          return clampPan(
            pointerX - (pointerX - previous.x) * ratio,
            pointerY - (pointerY - previous.y) * ratio,
            next,
          )
        })
        return next
      })
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  function changeZoom(factor: number) {
    setZoom((current) => {
      const next = clamp(current * factor, MIN_ZOOM, MAX_ZOOM)
      if (next === 1) setPan({ x: 0, y: 0 })
      else setPan((previous) => clampPan(previous.x, previous.y, next))
      return next
    })
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (zoom <= 1) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      panX: pan.x,
      panY: pan.y,
    }
    setDragging(true)
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragRef.current) return
    const deltaX = event.clientX - dragRef.current.pointerX
    const deltaY = event.clientY - dragRef.current.pointerY
    setPan(
      clampPan(
        dragRef.current.panX + deltaX,
        dragRef.current.panY + deltaY,
        zoom,
      ),
    )
  }

  function endDrag() {
    dragRef.current = null
    setDragging(false)
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/95 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Aperçu de l'image"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-full max-w-full flex-col items-center"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex w-full items-center justify-between gap-4 pb-3 text-[0.65rem] uppercase tracking-[0.18em] text-white/70">
          <span>
            Aperçu {sources.length > 1 ? `${index + 1} / ${sources.length}` : ''}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center border border-white/15 text-white/70 transition-colors hover:border-white/40 hover:text-white"
            aria-label="Fermer l'aperçu"
          >
            <X size={18} />
          </button>
        </div>

        <div
          ref={viewportRef}
          className={`relative flex max-h-[78vh] max-w-[92vw] touch-none items-center justify-center overflow-hidden ${
            zoom > 1 ? (dragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-zoom-in'
          }`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={resetView}
        >
          {!loaded && !failed && (
            <div className="absolute inset-0 grid place-items-center">
              <LoaderCircle size={28} className="animate-spin text-gold-400" />
            </div>
          )}
          {failed ? (
            <div className="px-8 py-16 text-sm text-white/70">
              Impossible de charger l'image.
            </div>
          ) : (
            <img
              src={srcWithVersion}
              alt="Image du média en grand"
              draggable={false}
              style={{
                transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
                transformOrigin: 'center',
              }}
              className={`max-h-[78vh] max-w-[92vw] select-none object-contain transition-opacity duration-300 ${
                loaded ? 'opacity-100' : 'opacity-0'
              }`}
              onLoad={() => setLoaded(true)}
              onError={() => setFailed(true)}
            />
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-[0.62rem] text-white/60">
          <button
            type="button"
            onClick={() => changeZoom(1 / 1.25)}
            disabled={zoom <= MIN_ZOOM}
            className="grid h-9 w-9 place-items-center border border-white/15 text-white/70 transition-colors hover:border-white/40 hover:text-white disabled:opacity-30"
            aria-label="Dézoomer"
          >
            <ZoomOut size={17} />
          </button>
          <span className="min-w-[4.5rem] text-center tabular-nums text-white/80">
            {Math.round(zoom * 100)} %
          </span>
          <button
            type="button"
            onClick={() => changeZoom(1.25)}
            disabled={zoom >= MAX_ZOOM}
            className="grid h-9 w-9 place-items-center border border-white/15 text-white/70 transition-colors hover:border-white/40 hover:text-white disabled:opacity-30"
            aria-label="Zoomer"
          >
            <ZoomIn size={17} />
          </button>
          <button
            type="button"
            onClick={resetView}
            className="inline-flex h-9 items-center gap-1.5 border border-white/15 px-2.5 text-[0.58rem] uppercase tracking-[0.14em] text-white/70 transition-colors hover:border-white/40 hover:text-white"
          >
            <RotateCcw size={13} />
            Réinitialiser
          </button>
          <span className="hidden items-center gap-1.5 sm:inline-flex">
            <Maximize2 size={12} />
            Molette pour zoomer · glisser pour déplacer
          </span>
        </div>

        {sources.length > 1 && (
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              disabled={index === 0}
              onClick={() => onIndexChange(index - 1)}
              className="grid h-9 w-9 place-items-center border border-white/15 text-white/70 transition-colors hover:border-white/40 hover:text-white disabled:opacity-30"
              aria-label="Image précédente"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              disabled={index === sources.length - 1}
              onClick={() => onIndexChange(index + 1)}
              className="grid h-9 w-9 place-items-center border border-white/15 text-white/70 transition-colors hover:border-white/40 hover:text-white disabled:opacity-30"
              aria-label="Image suivante"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
