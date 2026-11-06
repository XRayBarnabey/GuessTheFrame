import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  Film,
  Gauge,
  History,
  ImagePlus,
  Plus,
  Sparkles,
  Trash2,
  Trophy,
  Tv,
  UserRound,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import { api, errorMessage } from '../lib/api'
import type { HistoryPage, ProfileStats, ShowcaseItem, User } from '../lib/types'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorBanner, PageLoader, Stat } from '../components/ui'
import { Switch } from '../components/form'
import { SectionTitle } from '../components/Logo'

const KIND_LABELS: Record<ShowcaseItem['kind'], string> = {
  movie: 'Film',
  series: 'Série',
  anime: 'Anime',
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—'
  return `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ShowcaseArtwork({ item }: { item: ShowcaseItem }) {
  if (item.poster_url) {
    return (
      <img
        src={item.poster_url}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
      />
    )
  }
  const Icon = item.kind === 'movie' ? Film : item.kind === 'anime' ? Sparkles : Tv
  return (
    <div className="grid h-full w-full place-items-center text-sand-500">
      <Icon size={22} />
    </div>
  )
}

export function ProfilePage() {
  const { user, refresh } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [displayName, setDisplayName] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<ShowcaseItem[]>([])
  const [showcaseDirty, setShowcaseDirty] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const statsQuery = useQuery({
    queryKey: ['profile-stats'],
    queryFn: () => api.get<ProfileStats>('/api/users/me/stats'),
  })
  const historyQuery = useQuery({
    queryKey: ['profile-history', page],
    queryFn: () => api.get<HistoryPage>(`/api/users/me/games?page=${page}&page_size=10`),
  })
  const showcaseQuery = useQuery({
    queryKey: ['profile-showcase'],
    queryFn: () => api.get<{ items: ShowcaseItem[] }>('/api/users/me/showcase'),
  })
  const searchQuery = useQuery({
    queryKey: ['showcase-search', search],
    queryFn: () =>
      api.get<{ items: ShowcaseItem[] }>(
        `/api/users/me/showcase/search?q=${encodeURIComponent(search.trim())}`,
      ),
    enabled: search.trim().length >= 2,
  })

  useEffect(() => {
    if (user) setDisplayName(user.display_name ?? user.username)
  }, [user])

  useEffect(() => {
    if (showcaseQuery.data) {
      setSelected(showcaseQuery.data.items)
      setShowcaseDirty(false)
    }
  }, [showcaseQuery.data])

  const visibilityMutation = useMutation({
    mutationFn: (show: boolean) =>
      api.put('/api/users/me/preferences', { show_in_leaderboard: show }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['profile-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
      void refresh()
    },
  })

  const profileMutation = useMutation({
    mutationFn: () =>
      api.put<User>('/api/users/me/profile', {
        display_name: displayName.trim() || null,
      }),
    onSuccess: () => {
      setFeedback('Pseudo enregistré.')
      void refresh()
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const avatarMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('avatar', file)
      return api.upload<User>('/api/users/me/avatar', formData)
    },
    onSuccess: () => {
      setError(null)
      setFeedback('Image de profil mise à jour.')
      void refresh()
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const deleteAvatarMutation = useMutation({
    mutationFn: () => api.delete<User>('/api/users/me/avatar'),
    onSuccess: () => {
      setError(null)
      setFeedback('Image de profil supprimée.')
      void refresh()
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const showcaseMutation = useMutation({
    mutationFn: () =>
      api.put<{ items: ShowcaseItem[] }>('/api/users/me/showcase', {
        media_ids: selected.map((item) => item.media_id),
      }),
    onSuccess: (data) => {
      setSelected(data.items)
      setShowcaseDirty(false)
      setError(null)
      setFeedback('Vitrine enregistrée.')
      void queryClient.invalidateQueries({ queryKey: ['profile-showcase'] })
      void queryClient.invalidateQueries({ queryKey: ['showcase-search'] })
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  if (statsQuery.isLoading || historyQuery.isLoading || showcaseQuery.isLoading) {
    return <PageLoader />
  }
  if (
    statsQuery.isError ||
    historyQuery.isError ||
    showcaseQuery.isError ||
    !statsQuery.data ||
    !historyQuery.data ||
    !showcaseQuery.data
  ) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <ErrorBanner message="Impossible de charger votre profil." />
      </section>
    )
  }

  const stats = statsQuery.data
  const history = historyQuery.data
  const totalPages = Math.max(1, Math.ceil(history.total / history.page_size))
  const selectedIds = new Set(selected.map((item) => item.media_id))
  const suggestions = (searchQuery.data?.items ?? []).filter(
    (item) => !selectedIds.has(item.media_id),
  )
  const avatarLabel = (user?.display_name || user?.username || '?').slice(0, 2).toUpperCase()

  function addShowcaseItem(item: ShowcaseItem) {
    if (selected.length >= 5 || selectedIds.has(item.media_id)) return
    setSelected((current) => [...current, { ...item, poster_url: null }])
    setShowcaseDirty(true)
    setSearch('')
  }

  function removeShowcaseItem(mediaId: number) {
    setSelected((current) => current.filter((item) => item.media_id !== mediaId))
    setShowcaseDirty(true)
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <SectionTitle
          eyebrow="Profil"
          title={user?.display_name ?? user?.username ?? 'Votre parcours'}
          description="Personnalisez votre pseudo, votre image de profil et votre vitrine de contenus préférés. Vos statistiques restent basées sur les parties GuessTheFrame."
        />
        <div className="flex gap-2">
          <Link to="/leaderboard">
            <Button variant="secondary">
              <Trophy size={14} />
              Classement
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

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}
      {feedback && !error && (
        <div className="mt-4 flex items-center gap-2 border border-success-400/25 bg-success-400/[0.06] px-4 py-3 text-sm text-success-400">
          <Check size={16} />
          {feedback}
        </div>
      )}

      <section className="mt-7 grid gap-4 lg:grid-cols-[20rem_1fr]">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <UserRound size={14} />
            Identité
          </div>
          <div className="mt-4 flex items-center gap-4">
            <div className="relative h-24 w-24 shrink-0 overflow-hidden border border-cream-100/15 bg-ink-950">
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="grid h-full w-full place-items-center font-display text-3xl text-gold-300">
                  {avatarLabel}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-cream-100">
                {user?.display_name ?? user?.username}
              </div>
              <div className="mt-0.5 truncate text-xs text-sand-500">
                Compte Emby : {user?.username}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <label
                  className={clsx(
                    'inline-flex cursor-pointer items-center gap-1.5 border px-2.5 py-1.5 text-[0.65rem] transition-colors',
                    avatarMutation.isPending
                      ? 'pointer-events-none opacity-50'
                      : 'border-cream-100/15 text-sand-300 hover:border-gold-400/40 hover:text-cream-100',
                  )}
                >
                  <Camera size={13} />
                  {user?.avatar_url ? 'Changer' : 'Ajouter'}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    disabled={avatarMutation.isPending}
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      event.target.value = ''
                      if (file) avatarMutation.mutate(file)
                    }}
                  />
                </label>
                {user?.avatar_url && (
                  <Button
                    variant="ghost"
                    className="h-8 px-2.5 text-[0.65rem]"
                    loading={deleteAvatarMutation.isPending}
                    onClick={() => deleteAvatarMutation.mutate()}
                    title="Supprimer l’image de profil"
                  >
                    <Trash2 size={13} />
                  </Button>
                )}
              </div>
            </div>
          </div>

          <form
            className="mt-5"
            onSubmit={(event) => {
              event.preventDefault()
              setFeedback(null)
              setError(null)
              profileMutation.mutate()
            }}
          >
            <label className="block">
              <span className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">
                Pseudo affiché
              </span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={40}
                placeholder={user?.username}
                className="mt-2 h-10 w-full border border-cream-100/12 bg-ink-950/60 px-3 text-sm text-cream-100 outline-none focus:border-gold-400/60"
              />
            </label>
            <Button
              type="submit"
              className="mt-3 w-full"
              loading={profileMutation.isPending}
              disabled={displayName.trim().length === 1}
            >
              Enregistrer le pseudo
            </Button>
          </form>
        </Card>

        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <ImagePlus size={14} />
                Vitrine de contenus
              </div>
              <p className="mt-1 text-xs text-sand-500">
                Jusqu’à 5 films, séries ou animes préférés.
              </p>
            </div>
            <span className="text-xs text-sand-500">{selected.length}/5</span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {selected.map((item) => (
              <div
                key={item.media_id}
                className="group relative overflow-hidden border border-cream-100/10 bg-ink-950/40"
              >
                <div className="aspect-[2/3]">
                  <ShowcaseArtwork item={item} />
                </div>
                <button
                  type="button"
                  onClick={() => removeShowcaseItem(item.media_id)}
                  className="absolute right-2 top-2 grid h-6 w-6 place-items-center border border-white/25 bg-black/70 text-white/80 opacity-80 transition-opacity hover:text-white group-hover:opacity-100"
                  aria-label={`Retirer ${item.title}`}
                >
                  <X size={13} />
                </button>
                <div className="p-2">
                  <div className="line-clamp-2 text-xs font-medium text-cream-100">
                    {item.title}
                  </div>
                  <div className="mt-0.5 text-[0.58rem] uppercase tracking-[0.12em] text-sand-500">
                    {KIND_LABELS[item.kind]}
                    {item.year ? ` · ${item.year}` : ''}
                  </div>
                </div>
              </div>
            ))}
            {Array.from({ length: Math.max(0, 5 - selected.length) }).map((_, index) => (
              <div
                key={`empty-${index}`}
                className="grid aspect-[2/3] place-items-center border border-dashed border-cream-100/10 bg-ink-950/20 text-sand-600"
              >
                <Plus size={18} />
              </div>
            ))}
          </div>

          <div className="mt-4">
            <div className="relative">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Rechercher un film, une série ou un anime…"
                className="h-11 w-full border border-cream-100/12 bg-ink-950/60 px-3 text-sm text-cream-100 outline-none placeholder:text-sand-500/60 focus:border-gold-400/60"
                disabled={selected.length >= 5}
              />
              {search.trim().length >= 2 && selected.length < 5 && (
                <div className="absolute left-0 right-0 top-[calc(100%+0.35rem)] z-30 max-h-72 overflow-y-auto border border-cream-100/15 bg-ink-900 shadow-2xl shadow-black/30">
                  {searchQuery.isFetching && (
                    <div className="px-3 py-3 text-xs text-sand-500">Recherche…</div>
                  )}
                  {!searchQuery.isFetching && suggestions.length === 0 && (
                    <div className="px-3 py-3 text-xs text-sand-500">
                      Aucun contenu correspondant.
                    </div>
                  )}
                  {suggestions.map((item) => (
                    <button
                      key={item.media_id}
                      type="button"
                      onClick={() => addShowcaseItem(item)}
                      className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sand-400 transition-colors hover:bg-cream-100/[0.04] hover:text-cream-100"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        {item.kind === 'movie' ? (
                          <Film size={13} className="shrink-0 text-gold-400" />
                        ) : item.kind === 'anime' ? (
                          <Sparkles size={13} className="shrink-0 text-gold-400" />
                        ) : (
                          <Tv size={13} className="shrink-0 text-gold-400" />
                        )}
                        <span className="truncate text-sm">{item.title}</span>
                      </span>
                      <span className="shrink-0 text-[0.58rem] uppercase tracking-[0.12em] text-sand-500">
                        {KIND_LABELS[item.kind]}
                        {item.year ? ` · ${item.year}` : ''}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button
                loading={showcaseMutation.isPending}
                disabled={!showcaseDirty || selected.length > 5}
                onClick={() => {
                  setFeedback(null)
                  setError(null)
                  showcaseMutation.mutate()
                }}
              >
                Enregistrer la vitrine
              </Button>
              {showcaseDirty && (
                <span className="text-xs text-sand-500">Modifications non enregistrées</span>
              )}
            </div>
          </div>
        </Card>
      </section>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Parties jouées" value={stats.games} />
        <Stat label="Réussites" value={stats.wins} hint={`${stats.win_rate}% de réussite`} />
        <Stat label="Score cumulé" value={stats.score} hint={`meilleur : ${stats.best_score}`} />
        <Stat
          label="Tentatives moy."
          value={stats.avg_attempts || '—'}
          hint={
            stats.avg_duration_seconds
              ? `temps moy. ${formatDuration(stats.avg_duration_seconds)}`
              : undefined
          }
        />
      </div>

      <Card className="mt-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-medium text-cream-100">
            Apparaître dans le classement
          </div>
          <p className="mt-0.5 text-xs leading-relaxed text-sand-500">
            Désactivez cette option pour continuer à jouer et conserver vos statistiques
            personnelles sans apparaître dans le classement public.
          </p>
        </div>
        <Switch
          label="Apparaître dans le classement"
          checked={stats.show_in_leaderboard}
          disabled={visibilityMutation.isPending}
          onChange={(show) => visibilityMutation.mutate(show)}
        />
      </Card>
      {visibilityMutation.isError && (
        <div className="mt-3">
          <ErrorBanner message={errorMessage(visibilityMutation.error)} />
        </div>
      )}

      <section className="mt-10">
        <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
          <History size={14} />
          Historique
        </div>
        <h2 className="mt-2 font-display text-4xl tracking-wide text-cream-50">
          Vos dernières parties
        </h2>

        {history.items.length === 0 ? (
          <Card className="mt-5 p-8 text-center">
            <Gauge size={26} className="mx-auto text-sand-500" />
            <p className="mt-3 text-sm text-sand-400">
              Vous n’avez pas encore terminé de partie.
            </p>
            <Link to="/play" className="mt-5 inline-block">
              <Button>Lancer une partie</Button>
            </Link>
          </Card>
        ) : (
          <Card className="mt-5 divide-y divide-cream-100/[0.06]">
            {history.items.map((item) => (
              <div key={item.id} className="flex items-center gap-4 p-4 sm:p-5">
                <div className="h-20 w-14 shrink-0 overflow-hidden border border-cream-100/10 bg-ink-900">
                  {item.poster_url ? (
                    <img
                      src={item.poster_url}
                      alt=""
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="grid h-full w-full place-items-center text-sand-500">
                      <Film size={18} />
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/games/${item.id}/result`}
                      className="truncate text-sm font-medium text-cream-100 hover:text-gold-300"
                    >
                      {item.title ?? 'Média supprimé'}
                    </Link>
                    <span
                      className={clsx(
                        'border px-1.5 py-0.5 text-[0.55rem] uppercase tracking-[0.14em]',
                        item.status === 'won'
                          ? 'border-success-400/30 bg-success-400/10 text-success-400'
                          : 'border-danger-400/30 bg-danger-400/10 text-danger-400',
                      )}
                    >
                      {item.status === 'won'
                        ? 'Réussie'
                        : item.status === 'expired'
                          ? 'Expirée'
                          : 'Abandonnée'}
                    </span>
                  </div>
                  {item.subtitle && (
                    <div className="mt-0.5 truncate text-xs text-sand-500">
                      {item.subtitle}
                    </div>
                  )}
                  <div className="mt-1 text-[0.65rem] uppercase tracking-[0.12em] text-sand-500">
                    {formatDate(item.finished_at)} · {item.attempts_count} tentative(s) ·{' '}
                    {formatDuration(item.duration_seconds)}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-display text-2xl leading-none text-gold-400">
                    {item.score}
                  </div>
                  <div className="text-[0.55rem] uppercase tracking-[0.14em] text-sand-500">
                    points
                  </div>
                </div>
              </div>
            ))}
          </Card>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between gap-4">
            <span className="text-xs text-sand-500">
              Page {history.page} / {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                className="h-9 px-3"
                disabled={page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                <ChevronLeft size={15} />
                Précédent
              </Button>
              <Button
                variant="secondary"
                className="h-9 px-3"
                disabled={page >= totalPages}
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              >
                Suivant
                <ChevronRight size={15} />
              </Button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
