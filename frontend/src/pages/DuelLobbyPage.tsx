import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Dice5, Film, Link2, Sparkles, Swords, Tv } from 'lucide-react'
import clsx from 'clsx'
import { api, errorMessage } from '../lib/api'
import type { DuelState, DuelSummary, GameOptions } from '../lib/types'
import { Button, Card, ErrorBanner, InfoBanner, PageLoader } from '../components/ui'
import { SectionTitle } from '../components/Logo'

export function DuelLobbyPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const optionsQuery = useQuery({
    queryKey: ['game-options'],
    queryFn: () => api.get<GameOptions>('/api/game/options'),
  })
  const duelsQuery = useQuery({
    queryKey: ['my-duels'],
    queryFn: () => api.get<{ duels: DuelSummary[] }>('/api/duels/mine'),
    refetchInterval: 5000,
  })

  const [categories, setCategories] = useState<('movie' | 'series' | 'anime')[]>([
    'movie',
    'series',
    'anime',
  ])
  const [genres, setGenres] = useState<string[]>([])
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [createdCode, setCreatedCode] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<DuelState>('/api/duels', {
        categories,
        genres,
        library_ids: null,
      }),
    onSuccess: (duel) => {
      setCreatedCode(duel.code)
      queryClient.setQueryData(['duel', duel.id], duel)
      void queryClient.invalidateQueries({ queryKey: ['my-duels'] })
      navigate(`/duels/${duel.id}`)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const joinMutation = useMutation({
    mutationFn: () =>
      api.post<DuelState>('/api/duels/join', { code: code.trim() }),
    onSuccess: (duel) => {
      queryClient.setQueryData(['duel', duel.id], duel)
      navigate(`/duels/${duel.id}`)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  if (optionsQuery.isLoading) return <PageLoader />
  if (optionsQuery.isError || !optionsQuery.data) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <ErrorBanner message="Impossible de charger le catalogue pour le duel." />
      </section>
    )
  }
  const options = optionsQuery.data
  const activeDuels = (duelsQuery.data?.duels ?? []).filter(
    (duel) => duel.status !== 'finished' && duel.status !== 'cancelled',
  )

  function toggleCategory(value: 'movie' | 'series' | 'anime') {
    setCategories((current) => {
      if (current.includes(value)) {
        const next = current.filter((item) => item !== value)
        return next.length ? next : current
      }
      return [...current, value]
    })
  }

  function toggleGenre(name: string) {
    setGenres((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name],
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionTitle
          eyebrow="Duel 1v1"
          title="À deux, écran contre écran."
          description="Dix contenus distincts, cinq frames par joueur, un lancer de dés, un échange de frames et un chrono. Le meilleur enquêteur gagne."
        />
        <Link to="/">
          <Button variant="ghost">
            <ArrowLeft size={14} />
            Accueil
          </Button>
        </Link>
      </div>

      {error && (
        <div className="mt-5">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-7 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Card className="p-6">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <Swords size={14} />
            Créer un duel
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            Choisissez le terrain
          </h2>

          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <button
              type="button"
              onClick={() => toggleCategory('movie')}
              className={clsx(
                'flex items-center gap-3 border p-3 text-left text-sm transition-colors',
                categories.includes('movie')
                  ? 'border-gold-400/60 bg-gold-400/[0.08] text-cream-100'
                  : 'border-cream-100/10 bg-ink-950/40 text-sand-400',
              )}
            >
              <Film size={17} className="text-gold-400" />
              Films
            </button>
            <button
              type="button"
              onClick={() => toggleCategory('series')}
              className={clsx(
                'flex items-center gap-3 border p-3 text-left text-sm transition-colors',
                categories.includes('series')
                  ? 'border-gold-400/60 bg-gold-400/[0.08] text-cream-100'
                  : 'border-cream-100/10 bg-ink-950/40 text-sand-400',
              )}
            >
              <Tv size={17} className="text-gold-400" />
              Séries
            </button>
            <button
              type="button"
              onClick={() => toggleCategory('anime')}
              className={clsx(
                'flex items-center gap-3 border p-3 text-left text-sm transition-colors',
                categories.includes('anime')
                  ? 'border-gold-400/60 bg-gold-400/[0.08] text-cream-100'
                  : 'border-cream-100/10 bg-ink-950/40 text-sand-400',
              )}
            >
              <Sparkles size={17} className="text-gold-400" />
              Animes
            </button>
          </div>

          <div className="mt-5">
            <div className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
              Genres (optionnel)
            </div>
            <div className="mt-2 flex max-h-36 flex-wrap gap-1.5 overflow-y-auto pr-1">
              {options.genres.map((genre) => (
                <button
                  key={genre.name}
                  type="button"
                  onClick={() => toggleGenre(genre.name)}
                  className={clsx(
                    'border px-2.5 py-1 text-[0.68rem] transition-colors',
                    genres.includes(genre.name)
                      ? 'border-gold-400/60 bg-gold-400/10 text-gold-300'
                      : 'border-cream-100/10 bg-ink-950/40 text-sand-400 hover:text-cream-100',
                  )}
                >
                  {genre.name}
                </button>
              ))}
            </div>
          </div>

          <Button
            className="mt-5 w-full"
            loading={createMutation.isPending}
            onClick={() => {
              setError(null)
              createMutation.mutate()
            }}
          >
            <Dice5 size={15} />
            Créer le duel
          </Button>
          {createdCode && (
            <div className="mt-3 flex items-center gap-2 text-xs text-sand-500">
              Code créé : <strong className="text-gold-300">{createdCode}</strong>
            </div>
          )}
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <Link2 size={14} />
            Rejoindre un duel
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            Code de la salle
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-sand-500">
            Votre adversaire vous a partagé un code à 4 chiffres.
          </p>
          <input
            value={code}
            onChange={(event) =>
              setCode(event.target.value.replace(/\D/g, '').slice(0, 4))
            }
            placeholder="1234"
            inputMode="numeric"
            maxLength={4}
            className="mt-4 h-12 w-full border border-cream-100/12 bg-ink-950/60 px-4 text-center font-display text-2xl tracking-[0.25em] text-cream-100 outline-none focus:border-gold-400/60"
          />
          <Button
            variant="secondary"
            className="mt-3 w-full"
            loading={joinMutation.isPending}
            disabled={code.length !== 4}
            onClick={() => {
              setError(null)
              joinMutation.mutate()
            }}
          >
            Rejoindre
          </Button>

          {activeDuels.length > 0 && (
            <div className="mt-6 border-t border-cream-100/10 pt-4">
              <div className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                Vos duels en cours
              </div>
              <div className="mt-2 space-y-2">
                {activeDuels.slice(0, 4).map((duel) => (
                  <Link
                    key={duel.id}
                    to={`/duels/${duel.id}`}
                    className="flex items-center justify-between gap-3 border border-cream-100/10 bg-ink-950/40 px-3 py-2 text-xs text-sand-400 hover:border-gold-400/40 hover:text-cream-100"
                  >
                    <span className="font-mono tracking-[0.16em]">{duel.code}</span>
                    <span className="uppercase tracking-[0.12em]">{duel.phase}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-6">
        <InfoBanner>
          Déroulé : les 5 frames de chaque joueur apparaissent floutées pendant le lancer
          de dés, puis le jeu commence avec les frames visibles. Chacun lance un dé ; le
          meilleur score choisit le nombre de frames à échanger (0 à 5) et la durée
          (10 min par défaut). Les indices coûtent du temps, pas des points.
        </InfoBanner>
      </div>
    </div>
  )
}
