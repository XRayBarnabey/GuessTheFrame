import { useEffect, useState } from 'react'
import { LoaderCircle, RotateCcw, TriangleAlert } from 'lucide-react'
import clsx from 'clsx'

export function FrameImage({
  src,
  alt,
  version = 0,
  className,
}: {
  src: string
  alt: string
  version?: number
  className?: string
}) {
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  const [retry, setRetry] = useState(0)

  const effectiveSrc = `${src}${src.includes('?') ? '&' : '?'}v=${version}-${retry}`

  useEffect(() => {
    setLoaded(false)
    setFailed(false)
  }, [effectiveSrc])

  return (
    <div className={clsx('relative overflow-hidden border border-cream-100/10 bg-black', className)}>
      <div className="relative aspect-video w-full">
        {!loaded && !failed && (
          <div className="absolute inset-0 z-10 grid place-items-center bg-ink-950">
            <div className="text-center">
              <LoaderCircle size={26} className="mx-auto animate-spin text-gold-400" />
              <div className="mt-2 text-[0.6rem] uppercase tracking-[0.2em] text-sand-500">
                Extraction
              </div>
            </div>
          </div>
        )}
        {failed ? (
          <div className="absolute inset-0 grid place-items-center bg-ink-950 px-4 text-center">
            <div>
              <TriangleAlert size={22} className="mx-auto text-danger-400" />
              <div className="mt-2 text-xs text-cream-100">Image indisponible</div>
              <button
                type="button"
                onClick={() => {
                  setFailed(false)
                  setLoaded(false)
                  setRetry((value) => value + 1)
                }}
                className="mt-3 inline-flex items-center gap-1.5 text-[0.62rem] uppercase tracking-[0.14em] text-gold-300 hover:text-gold-200"
              >
                <RotateCcw size={12} />
                Réessayer
              </button>
            </div>
          </div>
        ) : (
          <img
            src={effectiveSrc}
            alt={alt}
            className={clsx(
              'h-full w-full object-contain transition-opacity duration-500',
              loaded ? 'opacity-100' : 'opacity-0',
            )}
            onLoad={() => {
              setLoaded(true)
              setFailed(false)
            }}
            onError={() => {
              setLoaded(false)
              setFailed(true)
            }}
          />
        )}
      </div>
    </div>
  )
}
