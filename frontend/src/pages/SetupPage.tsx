import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Film, PlugZap, ShieldCheck } from 'lucide-react'
import { api, errorMessage } from '../lib/api'
import type { SetupStatus } from '../lib/types'
import { Button, Card, ErrorBanner, InfoBanner, PageLoader, Spinner } from '../components/ui'
import { Field, Input, Checkbox } from '../components/form'
import { SectionTitle } from '../components/Logo'

type TestResult = {
  ok: boolean
  server_name: string
  server_version: string
  server_id: string
  libraries: { name: string; collection_type: string | null; item_count: number }[]
}

export function SetupPage() {
  const queryClient = useQueryClient()
  const statusQuery = useQuery({
    queryKey: ['setup-status'],
    queryFn: () => api.get<SetupStatus>('/api/setup/status'),
  })

  const [url, setUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [verifyTls, setVerifyTls] = useState(true)
  const [setupToken, setSetupToken] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [saved, setSaved] = useState<TestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const status = statusQuery.data
  const effectiveUrl = url || status?.emby_url || ''

  const testMutation = useMutation({
    mutationFn: () =>
      api.post<TestResult>('/api/setup/test', {
        url: effectiveUrl,
        api_key: apiKey,
        verify_tls: verifyTls,
        setup_token: setupToken,
      }),
    onSuccess: (result) => {
      setTestResult(result)
      setError(null)
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      api.post<TestResult>('/api/setup/emby', {
        url: effectiveUrl,
        api_key: apiKey,
        verify_tls: verifyTls,
        setup_token: setupToken,
      }),
    onSuccess: (result) => {
      setSaved(result)
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['setup-status'] })
    },
    onError: (exception) => setError(errorMessage(exception)),
  })

  if (statusQuery.isLoading) return <PageLoader />

  if (status?.setup_complete) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-14 sm:px-6">
        <Card className="p-6 sm:p-10">
          <div className="flex items-start gap-4">
            <span className="grid h-12 w-12 shrink-0 place-items-center border border-success-400/30 bg-success-400/10 text-success-400">
              <ShieldCheck size={22} />
            </span>
            <div>
              <h1 className="font-display text-4xl tracking-wide text-cream-50">
                Serveur Emby connecté
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-sand-400">
                {status.server_name ?? 'Emby'} · version {status.server_version ?? 'inconnue'}.
                Le catalogue peut maintenant être synchronisé depuis l'administration.
              </p>
            </div>
          </div>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <div className="border border-cream-100/[0.07] bg-ink-900/60 p-4">
              <div className="text-[0.62rem] uppercase tracking-[0.2em] text-sand-500">Serveur</div>
              <div className="mt-1 truncate text-sm text-cream-100">{status.emby_url}</div>
            </div>
            <div className="border border-cream-100/[0.07] bg-ink-900/60 p-4">
              <div className="text-[0.62rem] uppercase tracking-[0.2em] text-sand-500">FFmpeg</div>
              <div className="mt-1 text-sm text-cream-100">
                {status.ffmpeg.available ? 'Disponible' : 'Non détecté'}
              </div>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/login">
              <Button>Se connecter avec Emby</Button>
            </Link>
            <Link to="/admin">
              <Button variant="secondary">Administration</Button>
            </Link>
          </div>
        </Card>
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid gap-10 lg:grid-cols-[0.85fr_1.15fr] lg:gap-14">
        <div className="animate-rise">
          <SectionTitle
            eyebrow="Installation"
            title="Branchez votre serveur."
            description="GuessTheFrame utilise exclusivement les médias présents sur votre serveur Emby. Aucun catalogue externe n'est utilisé."
          />

          <ol className="mt-9 space-y-6">
            {[
              {
                icon: PlugZap,
                title: 'Adresse du serveur',
                text: 'Renseignez l’URL locale ou distante de votre serveur Emby, protocole inclus.',
              },
              {
                icon: ShieldCheck,
                title: 'Clé API dédiée',
                text: 'Dans Emby : Tableau de bord → Avancé → Sécurité → Ajouter. Créez une clé nommée GuessTheFrame.',
              },
              {
                icon: Film,
                title: 'Synchronisation',
                text: 'Les films et épisodes de vos bibliothèques seront importés dans le catalogue du jeu.',
              },
            ].map((step) => (
              <li key={step.title} className="flex gap-4">
                <span className="grid h-10 w-10 shrink-0 place-items-center border border-gold-400/25 bg-gold-400/[0.06] text-gold-300">
                  <step.icon size={18} strokeWidth={1.6} />
                </span>
                <div>
                  <div className="text-sm font-semibold text-cream-100">{step.title}</div>
                  <p className="mt-1 text-sm leading-relaxed text-sand-400">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-8">
            <InfoBanner>
              {status?.ffmpeg.available
                ? `FFmpeg est détecté (${status.ffmpeg.path}). Les frames pourront être extraites en haute qualité.`
                : 'FFmpeg n’est pas détecté. Les frames de secours d’Emby seront utilisées, en qualité réduite.'}
            </InfoBanner>
          </div>
        </div>

        <Card className="animate-rise-delay h-fit p-6 sm:p-8">
          <h2 className="font-display text-3xl tracking-wide text-cream-50">
            Configuration Emby
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-sand-500">
            Ces informations restent sur le serveur. La clé API est chiffrée en base et n’est
            jamais renvoyée au navigateur.
          </p>

          <form
            className="mt-7 space-y-5"
            onSubmit={(event) => {
              event.preventDefault()
              saveMutation.mutate()
            }}
          >
            <Field label="Adresse du serveur" hint="Exemple : http://192.168.1.50:8096">
              <Input
                value={effectiveUrl}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="http://192.168.1.50:8096"
                autoComplete="url"
                required
              />
            </Field>

            <Field label="Clé API Emby" hint="Créée dans le tableau de bord Emby, section Sécurité.">
              <Input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="••••••••••••••••"
                autoComplete="off"
                required
              />
            </Field>

            <Field
              label="Jeton d'installation"
              hint="Valeur GTF_SETUP_TOKEN du fichier .env local. Il protège la première configuration."
            >
              <Input
                type="password"
                value={setupToken}
                onChange={(event) => setSetupToken(event.target.value)}
                placeholder="Jeton affiché par scripts/setup.ps1"
                autoComplete="off"
                required
              />
            </Field>

            <Checkbox
              checked={verifyTls}
              onChange={setVerifyTls}
              label="Vérifier le certificat TLS (recommandé). Décochez uniquement pour un certificat auto-signé maîtrisé."
            />

            {error && <ErrorBanner message={error} />}

            {testResult && !error && (
              <div className="flex items-start gap-3 border border-success-400/25 bg-success-400/[0.06] px-4 py-3 text-sm text-success-400">
                <CheckCircle2 size={17} className="mt-0.5 shrink-0" />
                <span>
                  Connexion réussie à {testResult.server_name} ({testResult.server_version}).
                  {' '}
                  {testResult.libraries.length} bibliothèque(s) détectée(s).
                </span>
              </div>
            )}

            <div className="flex flex-wrap gap-3 pt-1">
              <Button
                type="button"
                variant="secondary"
                loading={testMutation.isPending}
                onClick={() => testMutation.mutate()}
                disabled={!effectiveUrl || !apiKey || !setupToken}
              >
                Tester
              </Button>
              <Button
                type="submit"
                loading={saveMutation.isPending}
                disabled={!effectiveUrl || !apiKey || !setupToken}
              >
                Enregistrer
              </Button>
            </div>
          </form>

          {saved && (
            <div className="mt-6 border-t border-cream-100/10 pt-5">
              <div className="flex items-center gap-2 text-sm text-success-400">
                <CheckCircle2 size={16} />
                Serveur enregistré.
              </div>
              <p className="mt-2 text-xs leading-relaxed text-sand-500">
                Bibliothèques actives par défaut : films et séries. Vous pourrez ajuster la
                sélection dans l’administration.
              </p>
              <div className="mt-4 flex gap-3">
                <Link to="/login">
                  <Button>Continuer vers la connexion</Button>
                </Link>
              </div>
            </div>
          )}

          {!status?.secrets_ready && (
            <div className="mt-6">
              <ErrorBanner message="GTF_ENCRYPTION_KEY n'est pas configurée. Lancez scripts/setup.ps1 avant de continuer." />
            </div>
          )}
        </Card>
      </div>

      {statusQuery.isError && (
        <div className="mt-8">
          <ErrorBanner message="Impossible de lire l'état de configuration du backend." />
        </div>
      )}
      {!status && <Spinner label="Lecture de la configuration" />}
    </section>
  )
}
