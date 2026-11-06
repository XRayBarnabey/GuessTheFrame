import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  Award,
  ExternalLink,
  Eye,
  Film,
  Lightbulb,
  RotateCcw,
  Trophy,
  Tv,
} from 'lucide-react'
import { api } from '../lib/api'
import type { GameResult, GameState } from '../lib/types'
import { Button, Card, ErrorBanner, PageLoader } from '../components/ui'

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes} min ${String(rest).padStart(2, '0')} s`
}

export function ResultPage() {
  const { gameId = '' } = useParams()
  const navigate = useNavigate()
  const [posterError, setPosterError] = useState(false)

  const gameQuery = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => api.get<GameState>(`/api/games/${gameId}`),
    enabled: Boolean(gameId),
    staleTime: 0,
  })
  const resultQuery = useQuery({
    queryKey: ['game-result', gameId],
    queryFn: () => api.get<GameResult>(`/api/games/${gameId}/result`),
    enabled: Boolean(gameId),
    retry: false,
  })

  const game = gameQuery.data
  const result = resultQuery.data

  useEffect(() => {
    if (game && game.status === 'in_progress') {
      navigate(`/games/${game.id}`, { replace: true })
    }
  }, [game, navigate])

  if (resultQuery.isLoading || gameQuery.isLoading) return <PageLoader />
  if (resultQuery.isError || !result) {
    return (
      <section className="mx-auto w-full max-w-3xl px-4 py-16">
        <ErrorBanner message="La partie n'est pas encore terminée ou le résultat est indisponible." />
        <div className="mt-6">
          <Link to={game ? `/games/${game.id}` : '/'}>
            <Button variant="secondary">
              <ArrowLeft size={15} />
              Retour à la partie
            </Button>
          </Link>
        </div>
      </section>
    )
  }

  const media = result.media
  const won = result.won
  const duration = result.duration_seconds
  const isEpisode = media.type === 'episode'
  const embyLabel = result.emby_server_name
    ? `Regarder sur ${result.emby_server_name}`
    : 'Regarder sur Emby'

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-gold-400">
            {won ? 'Bonne réponse' : 'Réponse révélée'}
          </span>
          <h1 className="mt-2 font-display text-5xl leading-none tracking-[0.02em] text-cream-50 sm:text-6xl">
            {won ? 'BIEN JOUÉ.' : 'FIN DE LA PARTIE.'}
          </h1>
        </div>
        <div className="flex items-end gap-4">
          <div className="text-right">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">Score</div>
            <div className="font-display text-6xl leading-none text-gold-400">{result.score}</div>
          </div>
          <div className="hidden h-14 w-px bg-cream-100/10 sm:block" />
          <div className="hidden text-right sm:block">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">Tentatives</div>
            <div className="font-display text-4xl leading-none text-cream-100">
              {result.attempts_count}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 grid gap-5 lg:grid-cols-[18rem_1fr]">
        <div className="mx-auto w-48 sm:w-56 lg:mx-0 lg:w-full">
          <div className="relative overflow-hidden border border-cream-100/10 bg-ink-900">
            {media.poster_url && !posterError ? (
              <img
                src={media.poster_url}
                alt={`Affiche de ${media.display_title}`}
                className="aspect-[2/3] w-full object-cover"
                onError={() => setPosterError(true)}
              />
            ) : (
              <div className="grid aspect-[2/3] w-full place-items-center bg-ink-900">
                <Film size={42} className="text-sand-500" />
              </div>
            )}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />
          </div>

          <Card className="mt-4 p-4">
            <div className="grid grid-cols-2 gap-3 text-center">
              <div>
                <div className="text-[0.58rem] uppercase tracking-[0.16em] text-sand-500">Durée</div>
                <div className="mt-1 text-xs text-cream-100">{formatDuration(duration)}</div>
              </div>
              <div>
                <div className="text-[0.58rem] uppercase tracking-[0.16em] text-sand-500">Indices</div>
                <div className="mt-1 text-xs text-cream-100">{result.hints_used.length}</div>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              {isEpisode ? (
                <span className="inline-flex items-center gap-1.5 border border-gold-400/25 bg-gold-400/[0.06] px-2.5 py-1 text-[0.6rem] uppercase tracking-[0.16em] text-gold-300">
                  <Tv size={12} />
                  Série
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 border border-gold-400/25 bg-gold-400/[0.06] px-2.5 py-1 text-[0.6rem] uppercase tracking-[0.16em] text-gold-300">
                  <Film size={12} />
                  Film
                </span>
              )}
              {media.year && (
                <span className="text-[0.65rem] uppercase tracking-[0.16em] text-sand-500">
                  {media.year}
                </span>
              )}
              {media.runtime_minutes && (
                <span className="text-[0.65rem] uppercase tracking-[0.16em] text-sand-500">
                  {media.runtime_minutes} min
                </span>
              )}
            </div>

            <h2 className="mt-3 font-display text-4xl leading-none tracking-[0.02em] text-cream-50 sm:text-5xl">
              {media.display_title}
            </h2>
            {isEpisode && media.episode_title && (
              <p className="mt-2 text-sm text-sand-400">
                Épisode : {media.episode_title}
                {media.season_number !== null && media.episode_number !== null
                  ? ` · S${String(media.season_number).padStart(2, '0')}E${String(media.episode_number).padStart(2, '0')}`
                  : ''}
              </p>
            )}
            {media.original_title && media.original_title !== media.display_title && (
              <p className="mt-1 text-xs italic text-sand-500">{media.original_title}</p>
            )}

            {(media.genres.length > 0 || media.directors.length > 0) && (
              <div className="mt-5 grid gap-4 border-t border-cream-100/[0.07] pt-4 sm:grid-cols-2">
                {media.directors.length > 0 && (
                  <div>
                    <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">
                      Réalisation
                    </div>
                    <div className="mt-1 text-sm text-cream-100">{media.directors.join(', ')}</div>
                  </div>
                )}
                {media.genres.length > 0 && (
                  <div>
                    <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">
                      Genres
                    </div>
                    <div className="mt-1 text-sm text-cream-100">{media.genres.join(', ')}</div>
                  </div>
                )}
              </div>
            )}

            {media.actors.length > 0 && (
              <div className="mt-4">
                <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">
                  Distribution
                </div>
                <div className="mt-1 text-sm text-cream-100">{media.actors.join(', ')}</div>
              </div>
            )}

            {media.overview && (
              <p className="mt-5 max-h-40 overflow-y-auto border-t border-cream-100/[0.07] pt-4 text-sm leading-relaxed text-sand-400">
                {media.overview}
              </p>
            )}

            <div className="mt-6 flex flex-wrap gap-3">
              <Button
                onClick={() =>
                  navigate('/play', {
                    state: game
                      ? {
                          filters: {
                            ...game.filters,
                            mode: game.mode === 'daily' ? 'classic' : game.mode,
                          },
                        }
                      : undefined,
                  })
                }
              >
                <RotateCcw size={15} />
                Nouvelle partie
              </Button>
              {media.emby_url && (
                <a href={media.emby_url} target="_blank" rel="noreferrer">
                  <Button variant="secondary">
                    <ExternalLink size={15} />
                    {embyLabel}
                  </Button>
                </a>
              )}
              <a href={`/api/games/${gameId}/frame`} target="_blank" rel="noreferrer">
                <Button variant="ghost">
                  <Eye size={15} />
                  Revoir la frame
                </Button>
              </a>
            </div>
            {!media.emby_url && (
              <p className="mt-3 text-[0.7rem] text-sand-500">
                Le lien Emby n’est pas disponible pour ce média (supprimé ou serveur non
                configuré).
              </p>
            )}
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="p-5">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <Lightbulb size={14} />
                Indices utilisés
              </div>
              {result.hints_used.length === 0 ? (
                <p className="mt-3 text-sm text-sand-400">Aucun indice. Beau travail.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {result.hints_used.map((hint) => (
                    <li key={hint.key} className="flex items-start justify-between gap-3 text-xs">
                      <span className="text-sand-500">{hint.label}</span>
                      <span className="text-right text-cream-100">{hint.value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <Award size={14} />
                Détail du score
              </div>
              <div className="mt-3 space-y-2 text-xs">
                <div className="flex justify-between gap-3">
                  <span className="text-sand-500">Tentatives</span>
                  <span className="text-cream-100">{result.attempts_count}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-sand-500">Temps</span>
                  <span className="text-cream-100">{formatDuration(duration)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-sand-500">Statut</span>
                  <span className={won ? 'text-success-400' : 'text-danger-400'}>
                    {won ? 'Réussie' : result.status === 'expired' ? 'Expirée' : 'Abandonnée'}
                  </span>
                </div>
                <div className="mt-2 border-t border-cream-100/10 pt-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="text-sand-400">Score final</span>
                    <span className="font-display text-2xl text-gold-400">{result.score}</span>
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link to="/leaderboard">
              <Button variant="ghost">
                <Trophy size={15} />
                Classement
                <ArrowRight size={14} />
              </Button>
            </Link>
            <Link to="/">
              <Button variant="ghost">
                <ArrowLeft size={14} />
                Accueil
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
