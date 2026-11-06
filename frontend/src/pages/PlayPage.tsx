import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  Film,
  Flame,
  Gauge,
  Images,
  Layers3,
  LayoutGrid,
  LibraryBig,
  Play,
  Tv,
  ZoomIn,
  type LucideIcon,
} from 'lucide-react'
import clsx from 'clsx'
import { api, ApiError, errorMessage } from '../lib/api'
import type { GameFilters, GameOptions, GameState } from '../lib/types'
import { Button, Card, ErrorBanner, InfoBanner, PageLoader } from '../components/ui'
import { SectionTitle } from '../components/Logo'
import { Checkbox } from '../components/form'

type GameMode = 'classic' | 'frames3' | 'frames5' | 'dezoom' | 'daily'

const MODES: {
  key: GameMode
  label: string
  description: string
  icon: LucideIcon
}[] = [
  {
    key: 'classic',
    label: 'Classique',
    description: 'Une seule frame mystère.',
    icon: Film,
  },
  {
    key: 'frames3',
    label: '3 frames',
    description: 'Trois images aléatoires du même contenu.',
    icon: Images,
  },
  {
    key: 'frames5',
    label: '5 frames',
    description: 'Cinq images pour multiplier les indices visuels.',
    icon: Layers3,
  },
  {
    key: 'dezoom',
    label: 'Dézoom',
    description: 'L’image est très zoomée, puis se dévoile à chaque erreur.',
    icon: ZoomIn,
  },
  {
    key: 'daily',
    label: 'Journalier',
    description: 'Le même film pour tous, une partie par jour.',
    icon: CalendarDays,
  },
]

const DIFFICULTY_LABELS: Record<string, { label: string; description: string }> = {
  easy: { label: 'Facile', description: 'Plus d’indices, erreurs sans pénalité.' },
  normal: { label: 'Normale', description: 'L’équilibre prévu par le jeu.' },
  hard: { label: 'Difficile', description: 'Moins d’indices, score plus élevé.' },
}

export function PlayPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()

  const optionsQuery = useQuery({
    queryKey: ['game-options'],
    queryFn: () => api.get<GameOptions>('/api/game/options'),
  })

  const previousFilters = (location.state as { filters?: GameFilters } | null)?.filters
  const initialMode: GameMode =
    previousFilters?.mode === 'frames3' ||
    previousFilters?.mode === 'frames5' ||
    previousFilters?.mode === 'dezoom'
      ? previousFilters.mode
      : 'classic'
  const [mediaTypes, setMediaTypes] = useState<('movie' | 'episode')[]>(
    previousFilters?.media_types ?? ['movie', 'episode'],
  )
  const [genres, setGenres] = useState<string[]>(previousFilters?.genres ?? [])
  const [libraries, setLibraries] = useState<string[]>(
    previousFilters?.library_ids ?? [],
  )
  const [difficulty, setDifficulty] = useState<'easy' | 'normal' | 'hard'>('normal')
  const [mode, setMode] = useState<GameMode>(initialMode)
  const [excludeSolved, setExcludeSolved] = useState(
    previousFilters?.exclude_solved ?? true,
  )
  const [error, setError] = useState<string | null>(null)
  const [activeGameId, setActiveGameId] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<GameState>('/api/games', {
        media_types: mediaTypes,
        genres,
        library_ids: libraries.length ? libraries : null,
        difficulty,
        mode,
        exclude_solved: excludeSolved,
      }),
    onSuccess: (game) => {
      queryClient.setQueryData(['game', game.id], game)
      navigate(`/games/${game.id}`)
    },
    onError: (exception) => {
      if (exception instanceof ApiError && exception.code === 'ACTIVE_GAME_EXISTS') {
        const details = (exception.details ?? {}) as { game_id?: string }
        setActiveGameId(details.game_id ?? null)
      } else {
        setActiveGameId(null)
      }
      setError(errorMessage(exception))
    },
  })

  const options = optionsQuery.data
  const selectedCount = useMemo(
    () =>
      (options?.types ?? [])
        .filter((type) => mediaTypes.includes(type.value))
        .reduce((total, type) => total + type.count, 0),
    [options, mediaTypes],
  )

  if (optionsQuery.isLoading) return <PageLoader />
  if (optionsQuery.isError || !options) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <ErrorBanner message="Impossible de charger les options de partie. Vérifiez le backend et le catalogue." />
      </section>
    )
  }

  const totalMedia = options.types.reduce((total, type) => total + type.count, 0)
  const allowLibraries = options.defaults.allow_library_filter

  function toggleType(value: 'movie' | 'episode') {
    setMediaTypes((current) => {
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

  function toggleLibrary(id: string) {
    setLibraries((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    )
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionTitle
          eyebrow="Nouvelle partie"
          title="Cadrez le sujet."
          description="Choisissez les films et séries qui peuvent tomber. Les filtres s’appliquent au catalogue réel synchronisé depuis Emby."
        />
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-sand-400 transition-colors hover:text-gold-300"
        >
          <ArrowLeft size={14} />
          Accueil
        </Link>
      </div>

      {totalMedia === 0 && (
        <div className="mt-6">
          <InfoBanner>
            Le catalogue est vide. Un administrateur doit lancer une synchronisation
            depuis l’administration.
          </InfoBanner>
        </div>
      )}

      <Card className="mt-6 p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
          <Play size={14} />
          Mode de jeu
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {MODES.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setMode(item.key)}
                className={clsx(
                  'border p-3 text-left transition-colors',
                  mode === item.key
                    ? 'border-gold-400/60 bg-gold-400/[0.08]'
                    : 'border-cream-100/10 bg-ink-950/40 hover:border-cream-100/25',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <Icon size={16} className="text-gold-400" />
                  {mode === item.key && <Check size={14} className="text-gold-300" />}
                </div>
                <div className="mt-2 text-xs font-semibold text-cream-100">{item.label}</div>
                <div className="mt-1 text-[0.64rem] leading-relaxed text-sand-500">
                  {item.description}
                </div>
              </button>
            )
          })}
        </div>
      </Card>

      {mode === 'daily' && (
        <div className="mt-4">
          <InfoBanner>
            Mode journalier : le film est identique pour tous les joueurs et vous ne pouvez
            jouer qu’une partie par jour. Les filtres ci-dessous sont ignorés.
          </InfoBanner>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <div className={clsx('space-y-6', mode === 'daily' && 'pointer-events-none opacity-40')}>
          <Card className="p-6">
            <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              <LayoutGrid size={14} />
              Type de contenu
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => toggleType('movie')}
                className={clsx(
                  'flex items-center gap-4 border p-4 text-left transition-all',
                  mediaTypes.includes('movie')
                    ? 'border-gold-400/60 bg-gold-400/[0.08]'
                    : 'border-cream-100/10 bg-ink-950/40 hover:border-cream-100/20',
                )}
              >
                <span className="grid h-10 w-10 place-items-center border border-gold-400/25 bg-gold-400/[0.06] text-gold-300">
                  <Film size={18} />
                </span>
                <span>
                  <span className="block text-sm font-semibold text-cream-100">Films</span>
                  <span className="text-xs text-sand-500">
                    {options.types.find((type) => type.value === 'movie')?.count ?? 0} disponible(s)
                  </span>
                </span>
                {mediaTypes.includes('movie') && (
                  <Check size={17} className="ml-auto text-gold-300" />
                )}
              </button>
              <button
                type="button"
                onClick={() => toggleType('episode')}
                className={clsx(
                  'flex items-center gap-4 border p-4 text-left transition-all',
                  mediaTypes.includes('episode')
                    ? 'border-gold-400/60 bg-gold-400/[0.08]'
                    : 'border-cream-100/10 bg-ink-950/40 hover:border-cream-100/20',
                )}
              >
                <span className="grid h-10 w-10 place-items-center border border-gold-400/25 bg-gold-400/[0.06] text-gold-300">
                  <Tv size={18} />
                </span>
                <span>
                  <span className="block text-sm font-semibold text-cream-100">Séries</span>
                  <span className="text-xs text-sand-500">
                    {options.types.find((type) => type.value === 'episode')?.count ?? 0} épisode(s)
                  </span>
                </span>
                {mediaTypes.includes('episode') && (
                  <Check size={17} className="ml-auto text-gold-300" />
                )}
              </button>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <Flame size={14} />
                Genres
              </div>
              {genres.length > 0 && (
                <button
                  type="button"
                  onClick={() => setGenres([])}
                  className="text-[0.65rem] uppercase tracking-[0.16em] text-sand-500 hover:text-gold-300"
                >
                  Tout retirer
                </button>
              )}
            </div>
            <p className="mt-1 text-xs text-sand-500">
              Aucun genre sélectionné = tous les genres autorisés.
            </p>
            <div className="mt-4 flex max-h-56 flex-wrap gap-2 overflow-y-auto pr-1">
              {options.genres.length === 0 && (
                <span className="text-sm text-sand-400">Aucun genre disponible.</span>
              )}
              {options.genres.map((genre) => (
                <button
                  key={genre.name}
                  type="button"
                  onClick={() => toggleGenre(genre.name)}
                  className={clsx(
                    'border px-3 py-1.5 text-xs transition-colors',
                    genres.includes(genre.name)
                      ? 'border-gold-400/60 bg-gold-400/10 text-gold-300'
                      : 'border-cream-100/10 bg-ink-950/40 text-sand-400 hover:border-cream-100/25 hover:text-cream-100',
                  )}
                >
                  {genre.name}
                  <span className="ml-1.5 text-[0.6rem] text-sand-500">{genre.media_count}</span>
                </button>
              ))}
            </div>
          </Card>

          {allowLibraries && options.libraries.length > 0 && (
            <Card className="p-6">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <LibraryBig size={14} />
                Bibliothèques
              </div>
              <p className="mt-1 text-xs text-sand-500">
                Aucune sélection = toutes les bibliothèques autorisées.
              </p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {options.libraries.map((library) => (
                  <button
                    key={library.id}
                    type="button"
                    onClick={() => toggleLibrary(library.id)}
                    className={clsx(
                      'flex items-center justify-between gap-3 border px-3 py-2 text-left text-xs transition-colors',
                      libraries.includes(library.id)
                        ? 'border-gold-400/50 bg-gold-400/[0.08] text-gold-200'
                        : 'border-cream-100/10 bg-ink-950/40 text-sand-400 hover:border-cream-100/20',
                    )}
                  >
                    <span className="truncate">{library.name}</span>
                    <span className="shrink-0 text-[0.6rem] text-sand-500">
                      {library.media_count}
                    </span>
                  </button>
                ))}
              </div>
            </Card>
          )}

          <Card className="p-6">
            <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              <Gauge size={14} />
              Difficulté
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {options.difficulties.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setDifficulty(item.key)}
                  className={clsx(
                    'border p-4 text-left transition-all',
                    difficulty === item.key
                      ? 'border-gold-400/60 bg-gold-400/[0.08]'
                      : 'border-cream-100/10 bg-ink-950/40 hover:border-cream-100/20',
                  )}
                >
                  <div className="text-sm font-semibold text-cream-100">
                    {DIFFICULTY_LABELS[item.key].label}
                  </div>
                  <div className="mt-1 text-[0.68rem] leading-relaxed text-sand-500">
                    {DIFFICULTY_LABELS[item.key].description}
                  </div>
                  <div className="mt-2 text-[0.62rem] uppercase tracking-[0.14em] text-gold-400">
                    {item.max_hints} indice(s) max
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-4">
              <Checkbox
                checked={excludeSolved}
                onChange={setExcludeSolved}
                label={`Exclure les médias déjà devinés (${options.excluded_solved} exclu(s))`}
              />
            </div>
          </Card>
        </div>

        <div className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="p-6">
            <div className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              Votre sélection
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sand-400">Types</span>
                <span className="text-cream-100">
                  {mediaTypes
                    .map((value) => (value === 'movie' ? 'Films' : 'Séries'))
                    .join(' + ')}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sand-400">Genres</span>
                <span className="max-w-[14rem] truncate text-cream-100">
                  {genres.length ? genres.join(', ') : 'Tous'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sand-400">Bibliothèques</span>
                <span className="text-cream-100">
                  {libraries.length ? `${libraries.length} sélectionnée(s)` : 'Toutes'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sand-400">Difficulté</span>
                <span className="text-cream-100">{DIFFICULTY_LABELS[difficulty].label}</span>
              </div>
            </div>

            <div className="mt-5 border-t border-cream-100/10 pt-4">
              <div className="flex items-end justify-between gap-3">
                <span className="text-xs text-sand-400">
                  {mode === 'daily' ? 'Défi du jour' : 'Médias correspondant aux types'}
                </span>
                <span className="font-display text-4xl leading-none text-gold-400">
                  {mode === 'daily' ? '1' : selectedCount}
                </span>
              </div>
            </div>

            {mode === 'daily' && (
              <p className="mt-3 text-[0.66rem] leading-relaxed text-sand-500">
                Difficulté normale · une seule tentative par jour · même film pour tous.
              </p>
            )}

            {error && (
              <div className="mt-4 space-y-3">
                <ErrorBanner message={error} />
                {activeGameId && (
                  <Link to={`/games/${activeGameId}`}>
                    <Button variant="secondary" className="w-full">
                      Reprendre la partie en cours
                    </Button>
                  </Link>
                )}
              </div>
            )}

            <Button
              type="button"
              className="mt-5 w-full"
              loading={createMutation.isPending}
              disabled={
                mode === 'daily'
                  ? (options.types.find((type) => type.value === 'movie')?.count ?? 0) === 0
                  : totalMedia === 0 || mediaTypes.length === 0
              }
              onClick={() => {
                setError(null)
                setActiveGameId(null)
                createMutation.mutate()
              }}
            >
              <Play size={15} />
              {mode === 'daily' ? 'Jouer le film du jour' : 'Lancer la partie'}
            </Button>
            <p className="mt-3 text-center text-[0.65rem] leading-relaxed text-sand-500">
              La réponse reste côté serveur. Aucun titre ne sera envoyé au navigateur avant
              la révélation.
            </p>
          </Card>

          <Card className="p-5">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">Astuce</div>
            <p className="mt-2 text-xs leading-relaxed text-sand-400">
              Commencez sans indice : une bonne réponse sans aide rapporte le maximum de
              points. Chaque indice réduit le score potentiel.
            </p>
          </Card>
        </div>
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Button variant="secondary" onClick={() => navigate('/')}>
          <ArrowLeft size={15} />
          Retour
        </Button>
        <Link to="/leaderboard">
          <Button variant="ghost">
            Voir le classement
            <ArrowRight size={15} />
          </Button>
        </Link>
      </div>
    </div>
  )
}
