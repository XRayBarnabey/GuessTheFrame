import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, LoaderCircle } from 'lucide-react'
import { api, ApiError, errorMessage } from '../lib/api'
import type { GameState } from '../lib/types'
import { Button, Card, ErrorBanner } from '../components/ui'

export function DailyPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const started = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [activeGameId, setActiveGameId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.post<GameState>('/api/games', { mode: 'daily' }),
    onSuccess: (game) => {
      queryClient.setQueryData(['game', game.id], game)
      navigate(`/games/${game.id}`, { replace: true })
    },
    onError: (exception) => {
      if (exception instanceof ApiError && exception.code === 'ACTIVE_GAME_EXISTS') {
        const details = (exception.details ?? {}) as { game_id?: string }
        setActiveGameId(details.game_id ?? null)
      }
      setError(errorMessage(exception))
    },
  })

  useEffect(() => {
    if (!started.current) {
      started.current = true
      mutation.mutate()
    }
  }, [mutation])

  return (
    <section className="mx-auto grid min-h-[65svh] w-full max-w-3xl place-items-center px-4 py-16">
      <Card className="w-full p-8 text-center sm:p-12">
        <span className="mx-auto grid h-14 w-14 place-items-center border border-gold-400/30 bg-gold-400/[0.08] text-gold-300">
          <CalendarDays size={24} />
        </span>
        <h1 className="mt-5 font-display text-5xl tracking-wide text-cream-50">
          Le film du jour
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-sand-400">
          Le même film pour tous les joueurs, une seule partie par jour. Préparez-vous à
          chercher.
        </p>

        {error ? (
          <div className="mx-auto mt-6 max-w-md">
            <ErrorBanner message={error} />
            <div className="mt-4 flex flex-wrap justify-center gap-3">
              <Button onClick={() => mutation.mutate()}>Réessayer</Button>
              {activeGameId && (
                <Link to={`/games/${activeGameId}`}>
                  <Button variant="secondary">Reprendre la partie en cours</Button>
                </Link>
              )}
              <Link to="/">
                <Button variant="ghost">
                  <ArrowLeft size={14} />
                  Accueil
                </Button>
              </Link>
            </div>
          </div>
        ) : (
          <div className="mt-7 flex items-center justify-center gap-3 text-xs uppercase tracking-[0.2em] text-sand-500">
            <LoaderCircle size={18} className="animate-spin text-gold-400" />
            Préparation du défi
          </div>
        )}
      </Card>
    </section>
  )
}
