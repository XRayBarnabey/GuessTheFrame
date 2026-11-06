import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Film,
  FolderSync,
  Gauge,
  HardDrive,
  KeyRound,
  RefreshCw,
  Server,
  Tags,
  Trash2,
  Tv,
  UserCog,
  Users,
} from 'lucide-react'
import { api, errorMessage } from '../lib/api'
import type {
  AdminGenre,
  AdminLibrary,
  AdminOverview,
  AdminSettings,
  AdminUsersResponse,
  CacheStatus,
  SyncStatus,
} from '../lib/types'
import { Button, Card, ErrorBanner, PageLoader, Spinner, Stat } from '../components/ui'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { SectionTitle } from '../components/Logo'
import { Checkbox, Input, Switch } from '../components/form'
import { AdminSettingsForm } from '../components/AdminSettingsForm'

type LibrariesResponse = { libraries: AdminLibrary[] }
type GenresResponse = { genres: AdminGenre[] }

export function AdminPage() {
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionInfo, setActionInfo] = useState<string | null>(null)
  const [embyUrl, setEmbyUrl] = useState('')
  const [embyKey, setEmbyKey] = useState('')
  const [embyVerify, setEmbyVerify] = useState(true)
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false)
  const [resetTarget, setResetTarget] = useState<{ id: number; username: string } | null>(
    null,
  )

  const overviewQuery = useQuery({
    queryKey: ['admin-overview'],
    queryFn: () => api.get<AdminOverview>('/api/admin/overview'),
  })
  const syncQuery = useQuery({
    queryKey: ['admin-sync'],
    queryFn: () => api.get<SyncStatus>('/api/admin/sync/status'),
    refetchInterval: (query) =>
      query.state.data?.running || query.state.data?.last_run?.status === 'running'
        ? 2500
        : false,
  })
  const librariesQuery = useQuery({
    queryKey: ['admin-libraries'],
    queryFn: () => api.get<LibrariesResponse>('/api/admin/libraries'),
  })
  const genresQuery = useQuery({
    queryKey: ['admin-genres'],
    queryFn: () => api.get<GenresResponse>('/api/admin/genres'),
  })
  const settingsQuery = useQuery({
    queryKey: ['admin-settings'],
    queryFn: () => api.get<AdminSettings>('/api/admin/settings'),
  })
  const cacheQuery = useQuery({
    queryKey: ['admin-cache'],
    queryFn: () => api.get<CacheStatus>('/api/admin/cache'),
  })
  const usersQuery = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get<AdminUsersResponse>('/api/admin/users'),
  })

  useEffect(() => {
    if (settingsQuery.data) {
      setEmbyUrl(settingsQuery.data.emby_url)
      setEmbyVerify(settingsQuery.data.emby_verify_tls)
    }
  }, [settingsQuery.data])

  const syncMutation = useMutation({
    mutationFn: () => api.post('/api/admin/sync'),
    onSuccess: () => {
      setActionError(null)
      setActionInfo('Synchronisation lancée en arrière-plan.')
      void queryClient.invalidateQueries({ queryKey: ['admin-sync'] })
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const libraryMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.put(`/api/admin/libraries/${encodeURIComponent(id)}`, {
        is_enabled: enabled,
      }),
    onSuccess: () => {
      setActionError(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-libraries'] })
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const genreMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.put(`/api/admin/genres/${encodeURIComponent(name)}`, {
        is_enabled: enabled,
      }),
    onSuccess: () => {
      setActionError(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-genres'] })
      void queryClient.invalidateQueries({ queryKey: ['catalogue-summary'] })
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const testMutation = useMutation({
    mutationFn: () => api.post<{ server_name: string; version: string }>('/api/admin/emby/test'),
    onSuccess: (result) => {
      setActionError(null)
      setActionInfo(`Connexion Emby réussie : ${result.server_name} (${result.version}).`)
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const purgeCacheMutation = useMutation({
    mutationFn: () => api.post<{ freed_megabytes: number }>('/api/admin/cache/purge'),
    onSuccess: (result) => {
      setShowPurgeConfirm(false)
      setActionError(null)
      setActionInfo(`Cache vidé (${result.freed_megabytes} Mo libérés).`)
      void queryClient.invalidateQueries({ queryKey: ['admin-cache'] })
    },
    onError: (exception) => {
      setShowPurgeConfirm(false)
      setActionError(errorMessage(exception))
    },
  })

  const userMutation = useMutation({
    mutationFn: ({
      id,
      is_admin,
      is_active,
    }: {
      id: number
      is_admin: boolean
      is_active: boolean
    }) => api.put(`/api/admin/users/${id}`, { is_admin, is_active }),
    onSuccess: () => {
      setActionError(null)
      void queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const embyConfigMutation = useMutation({
    mutationFn: () =>
      api.put<{ server_name: string; version: string; libraries: number }>(
        '/api/admin/emby',
        {
          url: embyUrl,
          api_key: embyKey.trim() || null,
          verify_tls: embyVerify,
        },
      ),
    onSuccess: (result) => {
      setActionError(null)
      setActionInfo(
        `Serveur Emby mis à jour : ${result.server_name} (${result.version}), ${result.libraries} bibliothèque(s).`,
      )
      setEmbyKey('')
      void queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-overview'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-libraries'] })
    },
    onError: (exception) => setActionError(errorMessage(exception)),
  })

  const resetHistoryMutation = useMutation({
    mutationFn: (userId: number) =>
      api.delete<{ deleted_games: number }>(`/api/admin/users/${userId}/history`),
    onSuccess: (result) => {
      setResetTarget(null)
      setActionError(null)
      setActionInfo(`${result.deleted_games} partie(s) supprimée(s) de l'historique.`)
      void queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      void queryClient.invalidateQueries({ queryKey: ['admin-overview'] })
      void queryClient.invalidateQueries({ queryKey: ['profile-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['profile-history'] })
      void queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
    },
    onError: (exception) => {
      setResetTarget(null)
      setActionError(errorMessage(exception))
    },
  })

  if (
    overviewQuery.isLoading ||
    syncQuery.isLoading ||
    librariesQuery.isLoading ||
    genresQuery.isLoading ||
    settingsQuery.isLoading
  ) {
    return <PageLoader />
  }

  if (
    overviewQuery.isError ||
    syncQuery.isError ||
    librariesQuery.isError ||
    genresQuery.isError ||
    settingsQuery.isError
  ) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <ErrorBanner message="Impossible de charger l'administration. Vérifiez le backend et vos droits." />
      </section>
    )
  }

  const overview = overviewQuery.data!
  const sync = syncQuery.data!
  const libraries = librariesQuery.data!.libraries
  const genres = genresQuery.data!.genres
  const settings = settingsQuery.data!
  const running = sync.running || sync.last_run?.status === 'running'
  const lastRun = sync.last_run

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <SectionTitle
          eyebrow="Administration"
          title="Le cockpit."
          description="Serveur Emby, synchronisation du catalogue, bibliothèques, genres et paramètres du jeu."
        />
        <div className="flex flex-wrap gap-3">
          <Button
            variant="secondary"
            loading={testMutation.isPending}
            onClick={() => testMutation.mutate()}
          >
            <Server size={15} />
            Tester Emby
          </Button>
          <Button loading={syncMutation.isPending} disabled={running} onClick={() => syncMutation.mutate()}>
            <RefreshCw size={15} className={running ? 'animate-spin' : ''} />
            {running ? 'Actualisation…' : 'Actualiser le catalogue'}
          </Button>
        </div>
      </div>

      {(actionError || actionInfo) && (
        <div className="mt-6 space-y-3">
          {actionError && <ErrorBanner message={actionError} />}
          {actionInfo && (
            <div className="flex items-center gap-2 border border-success-400/25 bg-success-400/[0.06] px-4 py-3 text-sm text-success-400">
              <CheckCircle2 size={16} />
              {actionInfo}
            </div>
          )}
        </div>
      )}

      <section className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Médias actifs" value={sync.catalogue.media} hint="films + épisodes" />
        <Stat label="Films" value={sync.catalogue.movies} />
        <Stat label="Épisodes" value={sync.catalogue.episodes} />
        <Stat label="Joueurs" value={overview.users} hint={`${overview.games} parties`} />
      </section>

      <div className="mt-10 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Card className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
                <FolderSync size={14} />
                Synchronisation
              </div>
              <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
                {running ? 'En cours…' : lastRun?.status === 'failed' ? 'Dernier essai échoué' : 'Catalogue à jour'}
              </h2>
            </div>
            {running ? (
              <Spinner label="Emby" />
            ) : lastRun?.status === 'success' ? (
              <CheckCircle2 size={22} className="text-success-400" />
            ) : lastRun?.status === 'failed' ? (
              <AlertTriangle size={22} className="text-danger-400" />
            ) : (
              <Database size={22} className="text-sand-500" />
            )}
          </div>

          {lastRun ? (
            <>
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ['Vus', lastRun.items_seen],
                  ['Ajoutés', lastRun.added],
                  ['Mis à jour', lastRun.updated],
                  ['Retirés', lastRun.deactivated],
                ].map(([label, value]) => (
                  <div key={String(label)} className="border border-cream-100/[0.07] bg-ink-950/40 px-3 py-3">
                    <div className="text-[0.58rem] uppercase tracking-[0.16em] text-sand-500">
                      {label}
                    </div>
                    <div className="mt-1 font-display text-2xl leading-none text-cream-100">
                      {value}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-xs leading-relaxed text-sand-500">
                Terminé le{' '}
                {lastRun.finished_at
                  ? new Date(lastRun.finished_at).toLocaleString('fr-FR')
                  : '—'}{' '}
                · {lastRun.libraries} bibliothèque(s) · {lastRun.errors} erreur(s).
              </div>
              {lastRun.error_message && (
                <div className="mt-3">
                  <ErrorBanner message={lastRun.error_message} />
                </div>
              )}
            </>
          ) : (
            <p className="mt-4 text-sm leading-relaxed text-sand-400">
              Aucune synchronisation n’a encore été lancée. Cliquez sur « Synchroniser »
              pour importer les films et épisodes de vos bibliothèques activées.
            </p>
          )}

          <div className="mt-5 grid gap-2 text-xs text-sand-500 sm:grid-cols-2">
            <div>
              Dernière synchro :{' '}
              {sync.last_sync_at
                ? new Date(sync.last_sync_at).toLocaleString('fr-FR')
                : 'jamais'}
            </div>
            <div>
              Automatique : {sync.sync_enabled ? 'tous les jours à 12:00' : 'désactivée'}
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <Server size={14} />
            Serveur Emby
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            {overview.emby.server_name ?? 'Non configuré'}
          </h2>
          <p className="mt-1 break-all text-xs text-sand-500">{overview.emby.url}</p>

          <div className="mt-5 space-y-3 border-t border-cream-100/[0.07] pt-4 text-sm">
            <div className="flex items-center justify-between gap-4">
              <span className="text-sand-400">Version</span>
              <span className="text-cream-100">{overview.emby.version ?? '—'}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-sand-400">Clé API</span>
              <span className={settings.emby_api_key_configured ? 'text-success-400' : 'text-danger-400'}>
                {settings.emby_api_key_configured ? 'configurée' : 'absente'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-sand-400">TLS vérifié</span>
              <span className="text-cream-100">{settings.emby_verify_tls ? 'oui' : 'non'}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-sand-400">Parties jouées</span>
              <span className="text-cream-100">
                {overview.games} · {overview.won} réussie(s)
              </span>
            </div>
          </div>

          <div className="mt-5 border-t border-cream-100/[0.07] pt-4">
            <div className="flex items-center gap-2 text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
              <KeyRound size={13} />
              Mettre à jour la connexion
            </div>
            <div className="mt-3 space-y-3">
              <Input
                value={embyUrl}
                onChange={(event) => setEmbyUrl(event.target.value)}
                placeholder="http://192.168.1.50:8096"
                aria-label="Adresse du serveur Emby"
              />
              <Input
                type="password"
                value={embyKey}
                onChange={(event) => setEmbyKey(event.target.value)}
                placeholder="Nouvelle clé API (laisser vide pour conserver)"
                autoComplete="off"
                aria-label="Nouvelle clé API Emby"
              />
              <Checkbox
                checked={embyVerify}
                onChange={setEmbyVerify}
                label="Vérifier le certificat TLS"
              />
              <Button
                variant="secondary"
                className="h-10"
                loading={embyConfigMutation.isPending}
                disabled={!embyUrl.trim()}
                onClick={() => embyConfigMutation.mutate()}
              >
                Mettre à jour Emby
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <Database size={14} />
            Bibliothèques
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            Sources autorisées
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-sand-500">
            Seules les bibliothèques activées sont synchronisées et proposées aux joueurs.
          </p>

          <div className="mt-5 divide-y divide-cream-100/[0.07]">
            {libraries.length === 0 && (
              <p className="py-6 text-sm text-sand-400">
                Aucune bibliothèque importée. Lancez une synchronisation.
              </p>
            )}
            {libraries.map((library) => (
              <div key={library.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm text-cream-100">
                    {library.collection_type === 'movies' ? (
                      <Film size={14} className="text-gold-400" />
                    ) : library.collection_type === 'tvshows' ? (
                      <Tv size={14} className="text-gold-400" />
                    ) : (
                      <Database size={14} className="text-sand-500" />
                    )}
                    <span className="truncate">{library.name}</span>
                  </div>
                  <div className="mt-0.5 text-[0.65rem] uppercase tracking-[0.14em] text-sand-500">
                    {library.collection_type ?? 'mixte'} · {library.item_count} média(s)
                  </div>
                </div>
                <Switch
                  label={`Activer ${library.name}`}
                  checked={library.is_enabled}
                  disabled={libraryMutation.isPending}
                  onChange={(enabled) =>
                    libraryMutation.mutate({ id: library.id, enabled })
                  }
                />
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            <Tags size={14} />
            Genres
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            Filtres disponibles
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-sand-500">
            Les genres proviennent du catalogue Emby. Désactivez ceux que vous ne voulez pas
            proposer dans les filtres de partie.
          </p>

          <div className="mt-5 max-h-[22rem] space-y-1 overflow-y-auto pr-1">
            {genres.length === 0 && (
              <p className="py-6 text-sm text-sand-400">
                Aucun genre importé. Lancez une synchronisation.
              </p>
            )}
            {genres.map((genre) => (
              <div key={genre.name} className="flex items-center justify-between gap-4 py-1.5">
                <div className="flex min-w-0 items-center gap-2 text-sm text-cream-100">
                  <span className="truncate">{genre.name}</span>
                  <span className="shrink-0 text-[0.62rem] text-sand-500">
                    {genre.media_count}
                  </span>
                </div>
                <Switch
                  label={`Activer ${genre.name}`}
                  checked={genre.is_enabled}
                  disabled={genreMutation.isPending}
                  onChange={(enabled) =>
                    genreMutation.mutate({ name: genre.name, enabled })
                  }
                />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="mt-6 p-6">
        <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
          <UserCog size={14} />
          Utilisateurs
        </div>
        <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
          Accès et rôles
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-sand-500">
          Les utilisateurs apparaissent après leur première connexion Emby. Désactiver un
          compte invalide immédiatement ses sessions GuessTheFrame.
        </p>

        <div className="mt-5 divide-y divide-cream-100/[0.07]">
          {(usersQuery.data?.users ?? []).length === 0 && (
            <p className="py-6 text-sm text-sand-400">Aucun utilisateur enregistré.</p>
          )}
          {(usersQuery.data?.users ?? []).map((user) => (
            <div
              key={user.id}
              className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-cream-100">{user.username}</span>
                  {user.is_admin && (
                    <span className="border border-gold-400/30 px-1.5 py-0.5 text-[0.55rem] uppercase tracking-[0.14em] text-gold-400">
                      Admin
                    </span>
                  )}
                  {!user.is_active && (
                    <span className="border border-danger-400/30 px-1.5 py-0.5 text-[0.55rem] uppercase tracking-[0.14em] text-danger-400">
                      Désactivé
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-[0.65rem] text-sand-500">
                  {user.games} partie(s) · {user.last_login_at
                    ? `vu le ${new Date(user.last_login_at).toLocaleDateString('fr-FR')}`
                    : 'jamais connecté'}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-5">
                <label className="flex items-center gap-2 text-[0.65rem] text-sand-400">
                  Administrateur
                  <Switch
                    label={`Administrateur ${user.username}`}
                    checked={user.is_admin}
                    disabled={userMutation.isPending}
                    onChange={(checked) =>
                      userMutation.mutate({
                        id: user.id,
                        is_admin: checked,
                        is_active: user.is_active,
                      })
                    }
                  />
                </label>
                <label className="flex items-center gap-2 text-[0.65rem] text-sand-400">
                  Actif
                  <Switch
                    label={`Activer ${user.username}`}
                    checked={user.is_active}
                    disabled={userMutation.isPending}
                    onChange={(checked) =>
                      userMutation.mutate({
                        id: user.id,
                        is_admin: user.is_admin,
                        is_active: checked,
                      })
                    }
                  />
                </label>
                <Button
                  variant="danger"
                  className="h-9 px-3"
                  onClick={() =>
                    setResetTarget({ id: user.id, username: user.username })
                  }
                >
                  <Trash2 size={13} />
                  Historique
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="mt-6 p-6">
        <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
          <Gauge size={14} />
          Barème et indices
        </div>
        <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
          Règles du jeu
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
            <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Score de base</div>
            <div className="mt-1 font-display text-3xl text-cream-100">
              {settings.game_config.base_points}
            </div>
          </div>
          <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
            <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Pénalité / erreur</div>
            <div className="mt-1 font-display text-3xl text-cream-100">
              −{settings.game_config.wrong_attempt_penalty}
            </div>
          </div>
          <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
            <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Indices normaux</div>
            <div className="mt-1 font-display text-3xl text-cream-100">
              {settings.difficulty_config.normal.max_hints}
            </div>
          </div>
          <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
            <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Joueurs</div>
            <div className="mt-1 flex items-center gap-2 font-display text-3xl text-cream-100">
              <Users size={20} className="text-gold-400" />
              {overview.users}
            </div>
          </div>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-sand-500">
          Ces paramètres sont calculés et appliqués côté serveur. Modifiez-les ci-dessous :
          les nouvelles parties utiliseront immédiatement le barème enregistré.
        </p>
      </Card>

      <AdminSettingsForm settings={settings} />

      <Card className="mt-6 p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
              <HardDrive size={14} />
              Cache des frames
            </div>
            <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
              Images extraites
            </h2>
          </div>
          <Button
            variant="danger"
            loading={purgeCacheMutation.isPending}
            onClick={() => setShowPurgeConfirm(true)}
          >
            <Trash2 size={15} />
            Vider le cache
          </Button>
        </div>
        {cacheQuery.data ? (
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
              <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Fichiers</div>
              <div className="mt-1 font-display text-3xl text-cream-100">
                {cacheQuery.data.files}
              </div>
            </div>
            <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
              <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Taille</div>
              <div className="mt-1 font-display text-3xl text-cream-100">
                {cacheQuery.data.megabytes} Mo
              </div>
            </div>
            <div className="border border-cream-100/[0.07] bg-ink-950/40 p-4">
              <div className="text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">Limite</div>
              <div className="mt-1 font-display text-3xl text-cream-100">
                {cacheQuery.data.max_megabytes} Mo
              </div>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-xs text-sand-500">Statistiques du cache indisponibles.</p>
        )}
      </Card>

      <ConfirmDialog
        open={showPurgeConfirm}
        title="Vider le cache des frames ?"
        description="Toutes les images extraites seront supprimées. Elles seront recalculées à la demande lors des prochaines parties."
        confirmLabel="Vider le cache"
        loading={purgeCacheMutation.isPending}
        onConfirm={() => {
          purgeCacheMutation.mutate()
        }}
        onClose={() => setShowPurgeConfirm(false)}
      />

      <ConfirmDialog
        open={resetTarget !== null}
        title={`Réinitialiser l'historique de ${resetTarget?.username ?? ''} ?`}
        description={
          <>
            Toutes les parties, statistiques, scores et indices de ce joueur seront
            supprimés définitivement. Son compte Emby et ses préférences sont conservés.
            Cette action est disponible uniquement depuis l'administration.
          </>
        }
        confirmLabel="Réinitialiser"
        loading={resetHistoryMutation.isPending}
        onConfirm={() => {
          if (resetTarget) resetHistoryMutation.mutate(resetTarget.id)
        }}
        onClose={() => setResetTarget(null)}
      />
    </div>
  )
}
