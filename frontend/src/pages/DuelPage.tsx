import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Check,
  Clipboard,
  Clock3,
  Copy,
  Dices,
  Eye,
  Flag,
  Handshake,
  Lightbulb,
  LogOut,
  Send,
  Swords,
  Trophy,
} from 'lucide-react'
import clsx from 'clsx'
import { api, ApiError, errorMessage } from '../lib/api'
import type { DuelProposal, DuelResult, DuelState } from '../lib/types'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorBanner, PageLoader, Spinner } from '../components/ui'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FrameImage } from '../components/FrameImage'
import { TitleAutocomplete } from '../components/TitleAutocomplete'

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

const PHASE_LABELS: Record<string, string> = {
  lobby: 'En attente',
  dice: 'Lancer de dés',
  settings: 'Réglages',
  exchange: 'Échange de frames',
  playing: 'En jeu',
  finished: 'Terminé',
}

export function DuelPage() {
  const { duelId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()

  const duelQuery = useQuery({
    queryKey: ['duel', duelId],
    queryFn: () => api.get<DuelState>(`/api/duels/${duelId}`),
    enabled: Boolean(duelId),
    refetchInterval: (query) =>
      query.state.data?.phase === 'playing' ? 1000 : 2000,
    staleTime: 0,
  })

  const [selectedFrameId, setSelectedFrameId] = useState<string | null>(null)
  const [guess, setGuess] = useState('')
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [exchangeCount, setExchangeCount] = useState(1)
  const [durationMinutes, setDurationMinutes] = useState(10)
  const [selectedFrames, setSelectedFrames] = useState<string[]>([])
  const [now, setNow] = useState(Date.now())
  const [confirmAbandon, setConfirmAbandon] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)

  const duel = duelQuery.data

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (duel?.phase === 'exchange') {
      setExchangeCount(duel.exchange_count)
    }
  }, [duel?.phase, duel?.exchange_count])

  useEffect(() => {
    setSelectedFrameId(null)
    setGuess('')
    setFeedback(null)
    setError(null)
    setSelectedFrames([])
  }, [duelId, duel?.phase])

  function applyState(state: DuelState) {
    queryClient.setQueryData(['duel', duelId], state)
  }

  const rollMutation = useMutation({
    mutationFn: () => api.post<DuelState>(`/api/duels/${duelId}/roll`),
    onSuccess: (state) => {
      setError(null)
      applyState(state)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const settingsMutation = useMutation({
    mutationFn: () =>
      api.post<DuelState>(`/api/duels/${duelId}/settings`, {
        exchange_count: exchangeCount,
        duration_seconds: durationMinutes * 60,
      }),
    onSuccess: (state) => {
      setError(null)
      applyState(state)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const exchangeMutation = useMutation({
    mutationFn: () =>
      api.post<DuelState>(`/api/duels/${duelId}/exchange`, {
        frame_ids: selectedFrames,
      }),
    onSuccess: (state) => {
      setError(null)
      applyState(state)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const abandonMutation = useMutation({
    mutationFn: () => api.post<DuelState>(`/api/duels/${duelId}/abandon`),
    onSuccess: (state) => {
      setError(null)
      setConfirmAbandon(false)
      applyState(state)
    },
    onError: (exception) => {
      setConfirmAbandon(false)
      setError(errorMessage(exception))
    },
  })

  const proposalMutation = useMutation({
    mutationFn: (type: DuelProposal['type']) =>
      api.post<DuelState>(`/api/duels/${duelId}/proposal`, { type }),
    onSuccess: (state) => {
      setError(null)
      setConfirmCancel(false)
      applyState(state)
    },
    onError: (exception) => {
      setConfirmCancel(false)
      setError(errorMessage(exception))
    },
  })

  const proposalResponseMutation = useMutation({
    mutationFn: (accept: boolean) =>
      api.post<DuelState>(`/api/duels/${duelId}/proposal/respond`, { accept }),
    onSuccess: (state) => {
      setError(null)
      applyState(state)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const guessMutation = useMutation({
    mutationFn: ({ frameId, value }: { frameId: string; value: string }) =>
      api.post<{ correct: boolean; state: DuelState }>(
        `/api/duels/${duelId}/frames/${frameId}/guess`,
        { guess: value },
      ),
    onSuccess: (response) => {
      setError(null)
      applyState(response.state)
      setFeedback(
        response.correct
          ? 'Bonne réponse ! Frame trouvée.'
          : 'Ce n’est pas la bonne réponse.',
      )
      setGuess('')
    },
    onError: (exception) => {
      if (exception instanceof ApiError && exception.code === 'DUEL_TIME_UP') {
        void duelQuery.refetch()
      }
      setError(errorMessage(exception))
    },
  })

  const hintMutation = useMutation({
    mutationFn: ({ frameId, key }: { frameId: string; key: string }) =>
      api.post<DuelState>(`/api/duels/${duelId}/frames/${frameId}/hints`, {
        hint_key: key,
      }),
    onSuccess: (state) => {
      setError(null)
      applyState(state)
      setFeedback(
        state.hint
          ? `Indice : ${state.hint.value} (−${state.hint_penalty_seconds}s sur votre chrono).`
          : `Indice révélé (−${state.hint_penalty_seconds}s sur votre chrono).`,
      )
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  if (duelQuery.isLoading) return <PageLoader />
  if (duelQuery.isError || !duel) {
    return (
      <section className="mx-auto w-full max-w-3xl px-4 py-16">
        <ErrorBanner message="Duel introuvable ou accès refusé." />
        <div className="mt-6">
          <Link to="/duel">
            <Button variant="secondary">
              <ArrowLeft size={15} />
              Retour aux duels
            </Button>
          </Link>
        </div>
      </section>
    )
  }

  const remaining = duel.you.deadline_at
    ? Math.max(0, Math.floor((new Date(duel.you.deadline_at).getTime() - now) / 1000))
    : null
  const opponent = duel.opponent
  const opponentRemaining = opponent?.deadline_at
    ? Math.max(0, Math.floor((new Date(opponent.deadline_at).getTime() - now) / 1000))
    : null
  const selectedFrame = duel.frames.find((frame) => frame.id === selectedFrameId) ?? null
  const isSetter = duel.settings_setter_id === user?.id
  const isFinished = duel.phase === 'finished'
  const result = isFinished ? (duel.result as DuelResult) : null
  const youTimedOut = remaining === 0 && !duel.you.finished
  const opponentTimedOut =
    opponentRemaining === 0 && !duel.opponent?.finished
  const canManageDuel =
    Boolean(duel.player2) &&
    !isFinished &&
    ['dice', 'settings', 'exchange', 'playing'].includes(duel.phase)
  const proposal = duel.proposal
  const phaseVersion = {
    lobby: 1,
    dice: 2,
    settings: 3,
    exchange: 4,
    playing: 5,
    finished: 6,
  }[duel.phase] ?? 1

  let timeoutNotice: {
    title: string
    text: string
    time: string | null
    timeLabel: string
  } | null = null
  if (
    youTimedOut &&
    opponent &&
    !opponent.finished &&
    opponentRemaining !== null &&
    opponentRemaining > 0
  ) {
    timeoutNotice = {
      title: 'Votre chrono est terminé',
      text: `${opponent.username} peut encore deviner.`,
      time: formatDuration(opponentRemaining),
      timeLabel: 'Temps restant de l’adversaire',
    }
  } else if (
    opponentTimedOut &&
    !duel.you.finished &&
    remaining !== null &&
    remaining > 0
  ) {
    timeoutNotice = {
      title: `Le chrono de ${opponent?.username ?? 'l’adversaire'} est terminé`,
      text: 'Vous pouvez encore deviner.',
      time: formatDuration(remaining),
      timeLabel: 'Votre temps restant',
    }
  } else if (youTimedOut && opponent?.finished) {
    timeoutNotice = {
      title: 'Votre chrono est terminé',
      text: `${opponent.username} a trouvé toutes ses frames.`,
      time: null,
      timeLabel: '',
    }
  } else if (opponentTimedOut && duel.you.finished) {
    timeoutNotice = {
      title: `Le chrono de ${opponent?.username ?? 'l’adversaire'} est terminé`,
      text: 'Vous avez trouvé toutes vos frames.',
      time: null,
      timeLabel: '',
    }
  } else if (youTimedOut && opponentTimedOut) {
    timeoutNotice = {
      title: 'Les deux chronos sont terminés',
      text: 'Les résultats sont en cours d’établissement.',
      time: null,
      timeLabel: '',
    }
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(duel?.code ?? '')
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-8 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/duel"
            className="grid h-9 w-9 place-items-center border border-cream-100/10 bg-ink-900/60 text-sand-400 hover:border-gold-400/40 hover:text-gold-300"
            aria-label="Retour aux duels"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.22em] text-gold-400">
              <Swords size={13} />
              Duel 1v1 · {PHASE_LABELS[duel.phase] ?? duel.phase}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-sand-500">
              <span>{duel.player1.username}</span>
              <span className="text-gold-400">vs</span>
              <span>{duel.player2.username ?? 'en attente…'}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {duel.phase === 'playing' && (
            <span className="inline-flex items-center gap-1.5 border border-gold-400/30 bg-gold-400/[0.08] px-3 py-2 text-[0.65rem] uppercase tracking-[0.14em] text-gold-300">
              <Clock3 size={13} />
              {formatDuration(remaining)}
            </span>
          )}
          <button
            type="button"
            onClick={copyCode}
            className="inline-flex items-center gap-1.5 border border-cream-100/10 bg-ink-900/60 px-3 py-2 text-[0.65rem] uppercase tracking-[0.14em] text-sand-400 hover:text-cream-100"
          >
            <Copy size={13} />
            {copied ? 'Copié' : `Code ${duel.code}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}

      {canManageDuel && (
        <Card className="mt-5 p-4">
          {proposal ? (
            proposal.by === user?.id ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-gold-400">
                    <Clock3 size={13} />
                    Proposition envoyée
                  </div>
                  <p className="mt-1 text-sm text-sand-400">
                    {proposal.type === 'cancel'
                      ? 'Vous avez proposé un match nul. La partie sera annulée si l’adversaire accepte.'
                      : 'Vous avez proposé de terminer maintenant. Le résultat sera établi avec la partie en l’état si l’adversaire accepte.'}
                  </p>
                </div>
                <span className="text-[0.62rem] uppercase tracking-[0.14em] text-sand-500">
                  En attente de l’adversaire…
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-gold-400">
                    <Handshake size={13} />
                    Proposition de l’adversaire
                  </div>
                  <p className="mt-1 text-sm text-cream-100">
                    {opponent?.username ?? 'L’adversaire'}{' '}
                    {proposal.type === 'cancel'
                      ? 'propose un match nul. La partie s’arrêtera et ne comptera pas dans le classement 1v1.'
                      : 'propose de terminer maintenant. Le résultat sera établi avec la partie en l’état.'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    loading={proposalResponseMutation.isPending}
                    onClick={() => proposalResponseMutation.mutate(true)}
                  >
                    Accepter
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={proposalResponseMutation.isPending}
                    onClick={() => proposalResponseMutation.mutate(false)}
                  >
                    Refuser
                  </Button>
                </div>
              </div>
            )
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                  <Flag size={13} className="text-gold-400" />
                  Fin de partie
                </div>
                <p className="mt-1 text-xs leading-relaxed text-sand-400">
                  Proposez de terminer maintenant, un match nul non classé, ou abandonnez
                  le duel.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  loading={proposalMutation.isPending}
                  onClick={() => proposalMutation.mutate('finish')}
                >
                  <Flag size={14} />
                  Proposer de terminer
                </Button>
                <Button
                  variant="ghost"
                  disabled={proposalMutation.isPending}
                  onClick={() => setConfirmCancel(true)}
                >
                  <Handshake size={14} />
                  Annuler la partie
                </Button>
                <Button
                  variant="danger"
                  disabled={proposalMutation.isPending}
                  onClick={() => setConfirmAbandon(true)}
                >
                  <LogOut size={14} />
                  Abandonner
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {duel.phase === 'lobby' && (
        <section className="mt-7 grid gap-6 lg:grid-cols-[1fr_20rem]">
          <div>
            <Card className="p-6">
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <Swords size={14} />
                Salle d’attente
              </div>
              <h1 className="mt-2 font-display text-4xl tracking-wide text-cream-50">
                En attente d’un adversaire.
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-sand-400">
                Partagez le code <strong className="text-gold-300">{duel.code}</strong> à
                votre adversaire. Les dix contenus sont préparés, mais les frames restent
                masquées tant que l’adversaire n’a pas rejoint la salle.
              </p>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button onClick={copyCode}>
                  <Clipboard size={15} />
                  Copier le code
                </Button>
                <Link to="/duel">
                  <Button variant="ghost">Annuler et revenir</Button>
                </Link>
              </div>
            </Card>
            <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={index}
                  className="grid aspect-video place-items-center border border-dashed border-cream-100/10 bg-ink-950/40 text-[0.62rem] uppercase tracking-[0.16em] text-sand-500"
                >
                  Frame masquée
                </div>
              ))}
            </div>
          </div>
          <Card className="h-fit p-5">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
              Règles
            </div>
            <p className="mt-2 text-xs leading-relaxed text-sand-400">
              Les deux joueurs partent avec 5 frames floutées. Après le lancer de dés, le
              gagnant choisit le nombre de frames à échanger et la durée. Les frames sont
              dévoilées pour la sélection, échangées, puis le jeu commence avec toutes les
              frames visibles.
            </p>
          </Card>
        </section>
      )}

      {duel.phase === 'dice' && (
        <section className="mt-7 grid gap-6 lg:grid-cols-2">
          <Card className="p-6">
            <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              <Dices size={14} />
              Lancer de dés
            </div>
            <h1 className="mt-2 font-display text-4xl tracking-wide text-cream-50">
              Que le sort décide.
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-sand-400">
              Chaque joueur lance un dé à 6 faces. Le plus haut score choisit les réglages.
              En cas d’égalité, on relance.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {[duel.you, duel.opponent].map((participant, index) =>
                participant ? (
                  <div
                    key={participant.user_id}
                    className={clsx(
                      'border p-4 text-center',
                      participant.user_id === user?.id
                        ? 'border-gold-400/40 bg-gold-400/[0.06]'
                        : 'border-cream-100/10 bg-ink-950/40',
                    )}
                  >
                    <div className="text-xs text-sand-400">
                      {participant.user_id === user?.id ? 'Vous' : participant.username}
                    </div>
                    <div className="mt-2 font-display text-5xl text-gold-300">
                      {participant.dice_value ??
                        (index === 0 ? duel.last_dice.player1 : duel.last_dice.player2) ??
                        '—'}
                    </div>
                  </div>
                ) : null,
              )}
            </div>
            {duel.last_dice.tie && (
              <p className="mt-4 text-sm text-danger-400">
                Égalité parfaite : relancez tous les deux.
              </p>
            )}
            <Button
              className="mt-5 w-full"
              loading={rollMutation.isPending}
              disabled={duel.you.dice_value !== null}
              onClick={() => rollMutation.mutate()}
            >
              <Dices size={15} />
              {duel.you.dice_value !== null ? 'Dé lancé' : 'Lancer mon dé'}
            </Button>
          </Card>
          <Card className="p-5">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
              Et ensuite
            </div>
            <p className="mt-2 text-xs leading-relaxed text-sand-400">
              Le gagnant du lancer pourra choisir entre 0 et 5 frames échangées, et une
              durée de 5 à 60 minutes (10 minutes par défaut).
            </p>
          </Card>
        </section>
      )}

      {duel.phase === 'settings' && (
        <section className="mt-7 grid gap-6 lg:grid-cols-2">
          <Card className="p-6">
            <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              <Dices size={14} />
              Réglages du duel
            </div>
            <h1 className="mt-2 font-display text-4xl tracking-wide text-cream-50">
              {isSetter ? 'À vous de fixer les règles.' : 'L’adversaire réfléchit…'}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-sand-400">
              {isSetter
                ? 'Choisissez le nombre de frames à échanger et la durée de la partie.'
                : `${duel.player1.username === user?.username ? duel.player2.username : duel.player1.username} a gagné le lancer et choisit les réglages.`}
            </p>

            {isSetter ? (
              <div className="mt-6 space-y-5">
                <label className="block">
                  <span className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                    Frames à échanger : {exchangeCount}
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={5}
                    value={exchangeCount}
                    onChange={(event) => setExchangeCount(Number(event.target.value))}
                    className="mt-3 w-full accent-[#d9b76f]"
                  />
                  <div className="mt-1 flex justify-between text-[0.6rem] text-sand-500">
                    <span>0</span>
                    <span>5</span>
                  </div>
                </label>
                <label className="block">
                  <span className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                    Durée (minutes)
                  </span>
                  <input
                    type="number"
                    min={5}
                    max={60}
                    value={durationMinutes}
                    onChange={(event) => setDurationMinutes(Number(event.target.value))}
                    className="mt-2 h-10 w-full border border-cream-100/12 bg-ink-950/60 px-3 text-sm text-cream-100 outline-none focus:border-gold-400/60"
                  />
                </label>
                <Button
                  className="w-full"
                  loading={settingsMutation.isPending}
                  onClick={() => settingsMutation.mutate()}
                >
                  Valider les réglages
                </Button>
              </div>
            ) : (
              <div className="mt-6">
                <Spinner label="En attente des réglages" />
              </div>
            )}
          </Card>
          <Card className="p-5">
            <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
              Dés
            </div>
            <div className="mt-3 flex items-center gap-6 font-display text-4xl text-gold-300">
              <span>{duel.last_dice.player1 ?? '—'}</span>
              <span className="text-sand-500">/</span>
              <span>{duel.last_dice.player2 ?? '—'}</span>
            </div>
          </Card>
        </section>
      )}

      {(duel.phase === 'dice' || duel.phase === 'settings') && (
        <section className="mt-6">
          <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
            <Eye size={13} className="text-gold-400" />
            Vos 5 frames, encore floutées
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {duel.frames.map((frame) => (
              <FrameImage
                key={frame.id}
                src={frame.image_url}
                alt={`Frame floutée ${frame.position + 1}`}
                version={phaseVersion}
              />
            ))}
          </div>
        </section>
      )}

      {duel.phase === 'exchange' && (
        <section className="mt-7">
          <Card className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                  <Eye size={14} />
                  Échange de frames
                </div>
                <h1 className="mt-2 font-display text-4xl tracking-wide text-cream-50">
                  Choisissez ce que vous donnez.
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-sand-400">
                  Sélectionnez exactement {duel.exchange_count} frame(s) parmi vos cinq.
                  Elles seront échangées avec celles de l’adversaire, puis le jeu commence
                  avec les frames visibles.
                </p>
              </div>
              <div className="text-right">
                <div className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                  Sélection
                </div>
                <div className="font-display text-4xl text-gold-400">
                  {selectedFrames.length}/{duel.exchange_count}
                </div>
              </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {duel.frames.map((frame) => {
                const selected = selectedFrames.includes(frame.id)
                return (
                  <button
                    key={frame.id}
                    type="button"
                    onClick={() => {
                      if (duel.you.submitted_exchange) return
                      setSelectedFrames((current) => {
                        if (current.includes(frame.id)) {
                          return current.filter((id) => id !== frame.id)
                        }
                        if (current.length >= duel.exchange_count) return current
                        return [...current, frame.id]
                      })
                    }}
                    className={clsx(
                      'relative text-left transition-all',
                      selected ? 'ring-2 ring-gold-400' : 'hover:opacity-90',
                    )}
                  >
                    <FrameImage
                      src={frame.image_url}
                      alt={`Frame à échanger ${frame.position + 1}`}
                      version={phaseVersion}
                    />
                    <span
                      className={clsx(
                        'absolute right-3 top-3 grid h-6 w-6 place-items-center border text-xs',
                        selected
                          ? 'border-gold-300 bg-gold-400 text-ink-950'
                          : 'border-white/30 bg-black/50 text-white/70',
                      )}
                    >
                      {selected ? <Check size={14} /> : ''}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button
                loading={exchangeMutation.isPending}
                disabled={
                  duel.you.submitted_exchange ||
                  selectedFrames.length !== duel.exchange_count
                }
                onClick={() => exchangeMutation.mutate()}
              >
                <Send size={15} />
                {duel.you.submitted_exchange ? 'Sélection envoyée' : 'Envoyer mon échange'}
              </Button>
              {duel.you.submitted_exchange && (
                <span className="text-xs text-sand-500">
                  En attente de l’adversaire…
                </span>
              )}
            </div>
          </Card>
        </section>
      )}

      {duel.phase === 'playing' && (
        <section className="mt-7">
          {timeoutNotice && (
            <Card className="mb-4 border border-gold-400/30 bg-gold-400/[0.06] p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-gold-400">
                    <Clock3 size={13} />
                    Chrono
                  </div>
                  <div className="mt-1 text-sm font-medium text-cream-100">
                    {timeoutNotice.title}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-sand-400">
                    {timeoutNotice.text}
                  </p>
                </div>
                {timeoutNotice.time && (
                  <div className="text-right">
                    <div className="text-[0.58rem] uppercase tracking-[0.14em] text-sand-500">
                      {timeoutNotice.timeLabel}
                    </div>
                    <div className="font-display text-4xl text-gold-300">
                      {timeoutNotice.time}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            {[duel.you, duel.opponent].map((participant) => {
              if (!participant) return null
              const isMe = participant.user_id === user?.id
              const participantRemaining = participant.deadline_at
                ? Math.max(
                    0,
                    Math.floor(
                      (new Date(participant.deadline_at).getTime() - now) / 1000,
                    ),
                  )
                : null
              const highlighted =
                (isMe &&
                  opponentTimedOut &&
                  !participant.finished &&
                  participantRemaining !== null &&
                  participantRemaining > 0) ||
                (!isMe &&
                  youTimedOut &&
                  !participant.finished &&
                  participantRemaining !== null &&
                  participantRemaining > 0)
              return (
                <Card
                  key={participant.user_id}
                  className={clsx(
                    'p-4',
                    highlighted && 'border border-gold-400/50 bg-gold-400/[0.06]',
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                        {isMe ? 'Vous' : 'Adversaire'}
                      </div>
                      <div className="mt-1 text-sm text-cream-100">
                        {participant.username}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-display text-3xl text-gold-400">
                        {participant.found}/5
                      </div>
                      <div className="text-[0.6rem] uppercase tracking-[0.14em] text-sand-500">
                        {participant.attempts} essai(s)
                      </div>
                    </div>
                  </div>
                  <div
                    className={clsx(
                      'mt-3 inline-flex items-center gap-1.5 border px-2.5 py-1 text-[0.68rem]',
                      highlighted
                        ? 'border-gold-400/50 bg-gold-400/10 text-gold-200'
                        : 'border-cream-100/10 bg-ink-950/40 text-sand-400',
                    )}
                  >
                    <Clock3 size={12} />
                    {participant.finished
                      ? 'Terminé'
                      : participantRemaining === null
                        ? '—'
                        : participantRemaining === 0
                          ? 'Temps écoulé'
                          : formatDuration(participantRemaining)}
                  </div>
                  {isMe && participant.hints > 0 && (
                    <div className="mt-2 text-[0.65rem] text-sand-500">
                      {participant.hints} indice(s) (−
                      {participant.hints * duel.hint_penalty_seconds}s)
                    </div>
                  )}
                  {participant.finished && (
                    <div className="mt-1 text-[0.65rem] text-success-400">
                      Toutes les frames trouvées.
                    </div>
                  )}
                </Card>
              )
            })}
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {duel.frames.map((frame) => (
              <button
                key={frame.id}
                type="button"
                onClick={() => {
                  setSelectedFrameId(frame.id)
                  setFeedback(null)
                  setError(null)
                }}
                className={clsx(
                  'relative text-left transition-all',
                  selectedFrameId === frame.id
                    ? 'ring-2 ring-gold-400'
                    : 'hover:opacity-90',
                )}
              >
                <FrameImage
                  src={frame.image_url}
                  alt={`Frame ${frame.position + 1}`}
                  version={phaseVersion + (frame.solved ? 10 : 0)}
                />
                {frame.solved && (
                  <div className="absolute inset-x-0 bottom-0 bg-black/75 px-3 py-2 text-xs text-cream-100">
                    {frame.media?.display_title ?? 'Trouvée'}
                  </div>
                )}
              </button>
            ))}
          </div>

          {selectedFrame && (
            <Card className="mt-5 p-5 sm:p-6">
              {selectedFrame.solved ? (
                <div>
                  <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-success-400">
                    <Check size={14} />
                    Frame trouvée
                  </div>
                  <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
                    {selectedFrame.media?.display_title}
                  </h2>
                  <p className="mt-1 text-sm text-sand-400">
                    {selectedFrame.media?.year ?? ''} ·{' '}
                    {selectedFrame.media?.type === 'episode' ? 'Série' : 'Film'}
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                        Frame {selectedFrame.position + 1}
                      </div>
                      <p className="mt-1 text-xs text-sand-500">
                        Proposez un titre, ou achetez un indice avec du temps.
                      </p>
                    </div>
                    <span className="text-[0.62rem] uppercase tracking-[0.14em] text-sand-500">
                      {youTimedOut
                        ? 'Temps écoulé'
                        : `${formatDuration(remaining)} restantes`}
                    </span>
                  </div>

                  <form
                    className="mt-4 flex flex-col gap-2 sm:flex-row"
                    onSubmit={(event) => {
                      event.preventDefault()
                      if (remaining === 0 || duel.you.finished) return
                      const value = guess.trim()
                      if (!value) return
                      setError(null)
                      guessMutation.mutate({
                        frameId: selectedFrame.id,
                        value,
                      })
                    }}
                  >
                    <TitleAutocomplete
                      value={guess}
                      onChange={setGuess}
                      inputId="duel-guess"
                      disabled={youTimedOut || duel.you.finished}
                    />
                    <Button
                      type="submit"
                      className="h-12 sm:w-auto"
                      loading={guessMutation.isPending}
                      disabled={!guess.trim() || youTimedOut || duel.you.finished}
                    >
                      <Send size={15} />
                      Valider
                    </Button>
                  </form>

                  {feedback && (
                    <p
                      className={clsx(
                        'mt-3 text-xs',
                        feedback.startsWith('Bonne') ? 'text-success-400' : 'text-danger-400',
                      )}
                    >
                      {feedback}
                    </p>
                  )}

                  <div className="mt-5 border-t border-cream-100/[0.07] pt-4">
                    <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                      <Lightbulb size={13} className="text-gold-400" />
                      Indices · chaque indice retire {duel.hint_penalty_seconds}s
                    </div>
                    {selectedFrame.hints_used.length > 0 && (
                      <ul className="mt-3 space-y-2">
                        {selectedFrame.hints_used.map((hint) => (
                          <li
                            key={hint.key}
                            className="border border-cream-100/[0.07] bg-ink-950/40 p-2.5"
                          >
                            <div className="text-[0.58rem] uppercase tracking-[0.14em] text-gold-400">
                              {hint.label}
                            </div>
                            <div className="mt-0.5 text-sm text-cream-100">{hint.value}</div>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedFrame.hint_options
                        .filter((option) => !option.used)
                        .map((option) => (
                          <button
                            key={option.key}
                            type="button"
                            disabled={hintMutation.isPending || youTimedOut}
                            onClick={() => {
                              setError(null)
                              hintMutation.mutate({
                                frameId: selectedFrame.id,
                                key: option.key,
                              })
                            }}
                            className="border border-cream-100/10 bg-ink-950/40 px-2.5 py-1.5 text-[0.68rem] text-sand-400 hover:border-gold-400/40 hover:text-cream-100 disabled:opacity-40"
                          >
                            {option.label}
                          </button>
                        ))}
                    </div>
                  </div>
                </>
              )}
            </Card>
          )}

          {duel.you.finished && (
            <Card className="mt-5 p-5 text-center">
              <Trophy size={22} className="mx-auto text-gold-400" />
              <p className="mt-2 text-sm text-cream-100">
                Vous avez trouvé vos 5 frames. En attente de l’adversaire.
              </p>
            </Card>
          )}
        </section>
      )}

      {isFinished && result && (
        <section className="mt-7 space-y-5">
          <Card className="p-6 text-center">
            <div className="flex flex-wrap items-center justify-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              {result.cancelled ? 'Duel annulé' : 'Fin du duel'}
              {result.ranked === false && (
                <span className="border border-sand-500/30 px-2 py-0.5 text-[0.55rem] tracking-[0.14em] text-sand-400">
                  Non classé
                </span>
              )}
            </div>
            <h1 className="mt-2 font-display text-5xl tracking-wide text-cream-50">
              {result.cancelled
                ? 'MATCH NUL.'
                : result.draw
                  ? 'ÉGALITÉ.'
                  : result.winner_id === user?.id
                    ? 'VICTOIRE.'
                    : 'DÉFAITE.'}
            </h1>
            <p className="mx-auto mt-2 max-w-2xl text-sm leading-relaxed text-sand-400">
              {result.cancelled
                ? 'La partie a été annulée d’un commun accord. Elle ne compte pas dans le classement 1v1.'
                : result.reason === 'abandon'
                  ? result.winner_id === user?.id
                    ? 'L’adversaire a abandonné. Vous remportez le duel.'
                    : 'Vous avez abandonné. L’adversaire remporte le duel.'
                  : result.reason === 'early_end'
                    ? 'La partie a été terminée d’un commun accord, dans son état actuel.'
                    : result.reason === 'completed'
                      ? 'Toutes les frames ont été trouvées.'
                      : result.reason === 'time'
                        ? 'Les chronos sont terminés. Le résultat est établi avec la partie en l’état.'
                        : result.draw
                          ? 'Les deux joueurs terminent à égalité.'
                          : `${result.winner_username} remporte le duel.`}
            </p>
            <div className="mx-auto mt-5 grid max-w-2xl gap-3 sm:grid-cols-2">
              {result.players.map((player) => (
                <div
                  key={player.user_id}
                  className={clsx(
                    'border p-4 text-left',
                    player.winner
                      ? 'border-gold-400/40 bg-gold-400/[0.06]'
                      : 'border-cream-100/10 bg-ink-950/40',
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-cream-100">{player.username}</span>
                    <span className="font-display text-2xl text-gold-400">
                      {player.found}/5
                    </span>
                  </div>
                  <div className="mt-1 text-[0.65rem] text-sand-500">
                    {player.attempts} tentative(s) · {player.hints} indice(s) ·{' '}
                    {player.time_penalty_seconds}s de pénalité
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <Button onClick={() => navigate('/duel')}>Nouveau duel</Button>
              <Link to="/leaderboard">
                <Button variant="ghost">
                  <Trophy size={14} />
                  Classement 1v1
                </Button>
              </Link>
            </div>
          </Card>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {result.frames.map((frame) => (
              <Card key={frame.id} className="overflow-hidden">
                <div className="relative">
                  <FrameImage
                    src={`/api/duels/${duel.id}/frames/${frame.id}`}
                    alt="Frame du duel"
                    version={99}
                  />
                  <div className="absolute inset-x-0 bottom-0 bg-black/75 px-3 py-2 text-xs text-cream-100">
                    {frame.media.display_title}
                  </div>
                </div>
                <div className="space-y-2 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[0.6rem] uppercase tracking-[0.12em]">
                    <span className="text-sand-500">
                      Frame de {frame.original_owner_username ?? 'un joueur'}
                    </span>
                    {(frame.exchanged ??
                    frame.original_owner_id !== frame.holder_id) ? (
                      <span className="border border-gold-400/30 bg-gold-400/10 px-1.5 py-0.5 text-gold-300">
                        Échangée → {frame.holder_username ?? 'l’adversaire'}
                      </span>
                    ) : (
                      <span className="text-sand-600">Non échangée</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-cream-100">
                      {frame.media.display_title}
                    </span>
                    <span className="border border-cream-100/10 px-1.5 py-0.5 text-[0.55rem] uppercase tracking-[0.12em] text-sand-500">
                      {frame.media.type === 'episode' ? 'Série' : 'Film'}
                    </span>
                  </div>
                  <div className="text-[0.65rem] text-sand-500">
                    {frame.media.year ?? 'Année inconnue'} ·{' '}
                    {frame.solved_by_username
                      ? `Trouvée par ${frame.solved_by_username}`
                      : frame.solved_by_user_id
                        ? 'Trouvée'
                        : 'Non trouvée'}
                  </div>
                  <div>
                    <div className="text-[0.58rem] uppercase tracking-[0.14em] text-gold-400">
                      Indices découverts
                    </div>
                    {(frame.hints ?? []).length === 0 ? (
                      <p className="mt-1 text-[0.65rem] text-sand-500">
                        Aucun indice utilisé.
                      </p>
                    ) : (
                      <ul className="mt-1 space-y-1">
                        {(frame.hints ?? []).map((hint, index) => (
                          <li
                            key={`${hint.user_id}-${hint.key}-${index}`}
                            className="text-[0.65rem] leading-relaxed text-sand-400"
                          >
                            <span className="text-cream-100">{hint.username}</span> ·{' '}
                            {hint.label} :{' '}
                            <span className="text-cream-100">{hint.value ?? '—'}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      <ConfirmDialog
        open={confirmAbandon}
        title="Abandonner le duel ?"
        description="L’adversaire sera déclaré vainqueur immédiatement. Le duel comptera dans le classement 1v1."
        confirmLabel="Abandonner"
        cancelLabel="Continuer"
        loading={abandonMutation.isPending}
        onConfirm={() => abandonMutation.mutate()}
        onClose={() => setConfirmAbandon(false)}
      />

      <ConfirmDialog
        open={confirmCancel}
        title="Annuler la partie ?"
        description="Une proposition de match nul sera envoyée à l’adversaire. Si elle est acceptée, la partie s’arrête et ne compte pas dans le classement 1v1."
        confirmLabel="Proposer le match nul"
        cancelLabel="Continuer"
        tone="primary"
        loading={proposalMutation.isPending}
        onConfirm={() => proposalMutation.mutate('cancel')}
        onClose={() => setConfirmCancel(false)}
      />
    </div>
  )
}
