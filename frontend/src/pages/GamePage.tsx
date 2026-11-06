import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Clock3,
  Eye,
  Flame,
  Lightbulb,
  Maximize2,
  Send,
  Skull,
  Sparkles,
  Trophy,
  ZoomIn,
} from 'lucide-react'
import clsx from 'clsx'
import { api, ApiError, errorMessage } from '../lib/api'
import type { AttemptResponse, GameState, Hint } from '../lib/types'
import { Button, Card, ErrorBanner, PageLoader, Spinner } from '../components/ui'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FrameImage } from '../components/FrameImage'
import { ImagePreviewModal } from '../components/ImagePreviewModal'
import { TitleAutocomplete } from '../components/TitleAutocomplete'

function formatDuration(seconds: number): string {
  const clamped = Math.max(0, seconds)
  const minutes = Math.floor(clamped / 60)
  const rest = clamped % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

export function GamePage() {
  const { gameId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const gameQuery = useQuery({
    queryKey: ['game', gameId],
    queryFn: () => api.get<GameState>(`/api/games/${gameId}`),
    enabled: Boolean(gameId),
    refetchOnWindowFocus: false,
  })

  const [guess, setGuess] = useState('')
  const [feedback, setFeedback] = useState<null | { type: 'wrong' | 'correct'; message: string }>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [unavailableHints, setUnavailableHints] = useState<string[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)
  const [showAbandonConfirm, setShowAbandonConfirm] = useState(false)

  const game = gameQuery.data

  useEffect(() => {
    setGuess('')
    setFeedback(null)
    setActionError(null)
    setUnavailableHints([])
    setPreviewIndex(null)
    setShowAbandonConfirm(false)
  }, [gameId])

  useEffect(() => {
    if (!game?.started_at) return
    const started = new Date(game.started_at).getTime()
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)))
    update()
    const interval = window.setInterval(update, 1000)
    return () => window.clearInterval(interval)
  }, [game?.started_at])

  useEffect(() => {
    if (game && game.status !== 'in_progress') {
      navigate(`/games/${game.id}/result`, { replace: true })
    }
  }, [game, navigate])

  const attemptMutation = useMutation({
    mutationFn: (value: string) =>
      api.post<AttemptResponse>(`/api/games/${gameId}/attempts`, { guess: value }),
    onSuccess: (response) => {
      setActionError(null)
      queryClient.setQueryData(['game', gameId], {
        ...response.state,
        ...(response.result ? { result: response.result } : {}),
      })
      if (response.correct && response.result) {
        setFeedback({ type: 'correct', message: 'Bonne réponse !' })
        queryClient.setQueryData(['game-result', gameId], response.result)
        void queryClient.invalidateQueries({ queryKey: ['catalogue-summary'] })
        void queryClient.invalidateQueries({ queryKey: ['profile-stats'] })
        void queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
        navigate(`/games/${gameId}/result`)
      } else {
        setFeedback({
          type: 'wrong',
          message:
            game?.mode === 'dezoom'
              ? 'Ce n’est pas la bonne réponse. Le zoom s’ouvre un peu plus.'
              : 'Ce n’est pas la bonne réponse. Continuez, ou demandez un indice.',
        })
        setGuess('')
      }
    },
    onError: (exception) => {
      if (exception instanceof ApiError && exception.code === 'GAME_ALREADY_FINISHED') {
        navigate(`/games/${gameId}/result`)
        return
      }
      setActionError(errorMessage(exception))
    },
  })

  const hintMutation = useMutation({
    mutationFn: (hintKey: string) =>
      api.post<GameState>(`/api/games/${gameId}/hints`, { hint_key: hintKey }),
    onSuccess: (state) => {
      setActionError(null)
      const hint = state.hint
      queryClient.setQueryData(['game', gameId], state)
      if (hint) {
        setFeedback({ type: 'correct', message: `Indice révélé : ${hint.label}.` })
      }
    },
    onError: (exception, hintKey) => {
      if (exception instanceof ApiError && exception.code === 'HINT_UNAVAILABLE') {
        setUnavailableHints((current) => [...new Set([...current, hintKey])])
      }
      setActionError(errorMessage(exception))
    },
  })

  const abandonMutation = useMutation({
    mutationFn: () => api.post(`/api/games/${gameId}/abandon`),
    onSuccess: () => {
      setShowAbandonConfirm(false)
      void queryClient.invalidateQueries({ queryKey: ['game', gameId] })
      navigate(`/games/${gameId}/result`)
    },
    onError: (exception) => {
      setShowAbandonConfirm(false)
      setActionError(errorMessage(exception))
    },
  })

  const hints = (game?.hints_used ?? []) as Hint[]
  const hintsLeft = game ? Math.max(0, game.max_hints - hints.length) : 0
  const hintChoices = (game?.hint_options ?? []).filter(
    (option) => !option.used && !unavailableHints.includes(option.key),
  )

  if (gameQuery.isLoading) return <PageLoader />
  if (gameQuery.isError || !game) {
    return (
      <section className="mx-auto w-full max-w-3xl px-4 py-16">
        <ErrorBanner message="Cette partie est introuvable ou ne vous appartient pas." />
        <div className="mt-6">
          <Link to="/">
            <Button variant="secondary">
              <ArrowLeft size={15} />
              Retour à l’accueil
            </Button>
          </Link>
        </div>
      </section>
    )
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const value = guess.trim()
    if (!value) return
    setFeedback(null)
    attemptMutation.mutate(value)
  }

  const frameVersion = game.mode === 'dezoom' ? game.attempts_count : 0
  const isDaily = game.mode === 'daily'
  const dailyLabel = game.daily_date
    ? new Date(`${game.daily_date}T12:00:00`).toLocaleDateString('fr-FR', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : ''
  const expiresLabel = game.expires_at
    ? new Date(game.expires_at).toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-14 pt-8 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="grid h-9 w-9 place-items-center border border-cream-100/10 bg-ink-900/60 text-sand-400 transition-colors hover:border-gold-400/40 hover:text-gold-300"
            aria-label="Quitter la partie"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="text-[0.62rem] font-semibold uppercase tracking-[0.22em] text-gold-400">
              {isDaily ? `Défi du ${dailyLabel}` : 'Partie en cours'}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-sand-500">
              <span>{game.mode_label}</span>
              <span>·</span>
              <span>
                Difficulté :{' '}
                {game.difficulty === 'easy'
                  ? 'facile'
                  : game.difficulty === 'hard'
                    ? 'difficile'
                    : 'normale'}
              </span>
              {game.mode === 'dezoom' && (
                <span className="inline-flex items-center gap-1 text-gold-400">
                  <ZoomIn size={12} />
                  ×{game.zoom_level}
                </span>
              )}
              {expiresLabel && (
                <span title="Sans activité, la partie est automatiquement abandonnée">
                  · reprise avant {expiresLabel}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[0.65rem] uppercase tracking-[0.14em] text-sand-400">
          <span className="inline-flex items-center gap-1.5 border border-cream-100/10 bg-ink-900/60 px-3 py-2">
            <Eye size={13} className="text-gold-400" />
            {game.attempts_count} tentative(s)
          </span>
          <span className="inline-flex items-center gap-1.5 border border-cream-100/10 bg-ink-900/60 px-3 py-2">
            <Lightbulb size={13} className="text-gold-400" />
            {hints.length}/{game.max_hints} indice(s)
          </span>
          <span className="inline-flex items-center gap-1.5 border border-cream-100/10 bg-ink-900/60 px-3 py-2">
            <Clock3 size={13} className="text-gold-400" />
            {formatDuration(elapsed)}
          </span>
          <span className="inline-flex items-center gap-1.5 border border-gold-400/30 bg-gold-400/[0.08] px-3 py-2 text-gold-300">
            <Flame size={13} />
            {game.score_potential} pts
          </span>
        </div>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div>
          <div className={clsx('grid gap-2', game.frame_count > 1 && 'sm:grid-cols-2')}>
            {game.frame_urls.map((url, index) => (
              <div key={url} className="relative">
                <FrameImage
                  src={url}
                  alt={`Image mystère ${index + 1} extraite du film ou de l’épisode`}
                  version={frameVersion}
                />
                <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-3">
                  <span className="text-[0.56rem] font-semibold uppercase tracking-[0.2em] text-white/60">
                    Frame {index + 1}/{game.frame_count}
                  </span>
                  {game.mode === 'dezoom' && (
                    <span className="border border-gold-400/30 bg-black/40 px-2 py-1 text-[0.56rem] uppercase tracking-[0.14em] text-[#f0d194]">
                      Zoom ×{game.zoom_level}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setPreviewIndex(index)}
                  className="absolute bottom-3 right-3 z-20 inline-flex items-center gap-1.5 border border-white/20 bg-black/60 px-2.5 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.14em] text-white/80 backdrop-blur transition-colors hover:border-gold-300/60 hover:text-white"
                  aria-label={`Agrandir l'image ${index + 1}`}
                >
                  <Maximize2 size={13} />
                  <span className="hidden sm:inline">Agrandir</span>
                </button>
              </div>
            ))}
          </div>

          <Card className="mt-5 p-5 sm:p-6">
            <form onSubmit={handleSubmit} className="space-y-3">
              <label
                htmlFor="guess"
                className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-sand-400"
              >
                Votre réponse
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <TitleAutocomplete value={guess} onChange={setGuess} />
                <Button
                  type="submit"
                  className="h-12 sm:w-auto"
                  loading={attemptMutation.isPending}
                  disabled={!guess.trim()}
                >
                  <Send size={15} />
                  Valider
                </Button>
              </div>
              <p className="text-[0.65rem] text-sand-500">
                La liste de suggestions est issue de votre catalogue Emby : sélectionnez un
                titre pour éviter les fautes de frappe.
              </p>
            </form>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="danger"
                className="h-10"
                loading={abandonMutation.isPending}
                onClick={() => setShowAbandonConfirm(true)}
              >
                <Skull size={15} />
                Abandonner
              </Button>
              <Link to="/leaderboard">
                <Button type="button" variant="ghost" className="h-10">
                  <Trophy size={15} />
                  Classement
                </Button>
              </Link>
            </div>

            <div aria-live="polite" className="mt-3 min-h-5">
              {feedback && (
                <p
                  className={clsx(
                    'text-xs',
                    feedback.type === 'wrong' ? 'text-danger-400' : 'text-success-400',
                  )}
                >
                  {feedback.message}
                </p>
              )}
              {actionError && (
                <div className="mt-2">
                  <ErrorBanner message={actionError} />
                </div>
              )}
            </div>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <Lightbulb size={14} />
                Indices
              </div>
              <span className="text-[0.62rem] uppercase tracking-[0.14em] text-sand-500">
                {hintsLeft} restant(s)
              </span>
            </div>

            {hintsLeft > 0 && hintChoices.length > 0 ? (
              <div className="mt-4">
                <div className="text-[0.6rem] uppercase tracking-[0.16em] text-sand-500">
                  Choisissez un indice
                </div>
                <div className="mt-2 grid gap-2">
                  {hintChoices.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      disabled={hintMutation.isPending}
                      onClick={() => {
                        setFeedback(null)
                        setActionError(null)
                        hintMutation.mutate(option.key)
                      }}
                      className="flex items-center justify-between gap-3 border border-cream-100/10 bg-ink-950/40 px-3 py-2 text-left text-xs text-sand-400 transition-colors hover:border-gold-400/40 hover:text-cream-100 disabled:opacity-50"
                    >
                      <span className="inline-flex items-center gap-2">
                        <Sparkles size={12} className="text-gold-400" />
                        {option.label}
                      </span>
                      <span className="shrink-0 text-[0.6rem] text-sand-500">
                        −{option.penalty} pts
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="mt-4 text-xs leading-relaxed text-sand-500">
                {hintsLeft === 0
                  ? 'Limite d’indices atteinte pour cette difficulté.'
                  : 'Aucun indice supplémentaire disponible pour ce média.'}
              </p>
            )}

            {hints.length > 0 && (
              <ul className="mt-5 space-y-3 border-t border-cream-100/[0.07] pt-4">
                {hints.map((hint) => (
                  <li key={hint.key} className="border border-cream-100/[0.07] bg-ink-950/40 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[0.6rem] uppercase tracking-[0.16em] text-gold-400">
                        {hint.label}
                      </span>
                      <span className="text-[0.6rem] text-sand-500">−{hint.penalty} pts</span>
                    </div>
                    <div className="mt-1 text-sm text-cream-100">{hint.value}</div>
                  </li>
                ))}
              </ul>
            )}

            {hintMutation.isPending && (
              <div className="mt-4">
                <Spinner label="Recherche de l’indice" />
              </div>
            )}
          </Card>

          <Card className="p-5">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">Rappel</div>
            <p className="mt-2 text-xs leading-relaxed text-sand-400">
              Pour une série, la réponse attendue est le nom de la série. Le nom de
              l’épisode est un indice, jamais la réponse. Les indices ne peuvent jamais
              être la réponse.
            </p>
          </Card>
        </aside>
      </div>

      {previewIndex !== null && (
        <ImagePreviewModal
          sources={game.frame_urls}
          index={previewIndex}
          onIndexChange={setPreviewIndex}
          onClose={() => setPreviewIndex(null)}
          version={frameVersion}
        />
      )}

      <ConfirmDialog
        open={showAbandonConfirm}
        title="Abandonner la partie ?"
        description={
          <>
            La réponse sera révélée et la partie sera enregistrée comme abandonnée avec
            <strong className="text-cream-100"> 0 point</strong>. Cette action est
            définitive.
          </>
        }
        confirmLabel="Oui, abandonner"
        cancelLabel="Continuer à jouer"
        loading={abandonMutation.isPending}
        onConfirm={() => abandonMutation.mutate()}
        onClose={() => setShowAbandonConfirm(false)}
      />
    </div>
  )
}
