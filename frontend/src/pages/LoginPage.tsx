import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, LockKeyhole, Server, UserRound } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { api, errorMessage } from '../lib/api'
import type { SetupStatus } from '../lib/types'
import { Button, Card, ErrorBanner, PageLoader } from '../components/ui'
import { Field, Input } from '../components/form'

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const statusQuery = useQuery({
    queryKey: ['setup-status'],
    queryFn: () => api.get<SetupStatus>('/api/setup/status'),
  })

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) return <PageLoader />
  if (user) return <Navigate to={from} replace />

  const status = statusQuery.data

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
      navigate(from, { replace: true })
    } catch (exception) {
      setError(errorMessage(exception))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[1fr_0.9fr] lg:items-center lg:gap-16 lg:px-8 lg:py-20">
      <div className="animate-rise">
        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-gold-400">
          Votre serveur, vos films
        </span>
        <h1 className="mt-4 font-display text-6xl leading-[0.92] tracking-[0.02em] text-cream-50 sm:text-7xl">
          UNE IMAGE.
          <br />
          <span className="text-gold-400">UN FILM.</span>
          <br />
          À VOUS DE JOUER.
        </h1>
        <p className="mt-6 max-w-lg text-sm leading-relaxed text-sand-400 sm:text-base">
          Connectez-vous avec votre compte Emby existant. Aucun nouveau compte à créer :
          votre identifiant Emby est votre identité de joueur.
        </p>

        <div className="mt-9 grid gap-3 sm:grid-cols-2">
          <div className="border border-cream-100/[0.07] bg-ink-900/50 p-4">
            <Server size={17} className="text-gold-400" />
            <div className="mt-3 text-[0.62rem] uppercase tracking-[0.2em] text-sand-500">
              Serveur
            </div>
            <div className="mt-1 truncate text-sm text-cream-100">
              {status?.server_name ?? 'Non configuré'}
            </div>
            <div className="mt-0.5 text-[0.7rem] text-sand-500">
              {status?.server_version ? `Emby ${status.server_version}` : '—'}
            </div>
          </div>
          <div className="border border-cream-100/[0.07] bg-ink-900/50 p-4">
            <LockKeyhole size={17} className="text-gold-400" />
            <div className="mt-3 text-[0.62rem] uppercase tracking-[0.2em] text-sand-500">
              Sécurité
            </div>
            <div className="mt-1 text-sm text-cream-100">Mot de passe jamais stocké</div>
            <div className="mt-0.5 text-[0.7rem] text-sand-500">
              Session HttpOnly · token Emby chiffré
            </div>
          </div>
        </div>
      </div>

      <Card className="animate-rise-delay w-full p-6 sm:p-8">
        <h2 className="font-display text-3xl tracking-wide text-cream-50">
          Connexion Emby
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-sand-500">
          Utilisez vos identifiants Emby habituels.
        </p>

        {statusQuery.isLoading ? (
          <div className="mt-8">
            <PageLoader />
          </div>
        ) : !status?.setup_complete ? (
          <div className="mt-8 space-y-5">
            <ErrorBanner message="Aucun serveur Emby n'est encore configuré." />
            <Link to="/setup">
              <Button>
                Configurer le serveur
                <ArrowRight size={15} />
              </Button>
            </Link>
          </div>
        ) : (
          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <Field label="Nom d'utilisateur Emby">
              <div className="relative">
                <UserRound
                  size={16}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sand-500"
                />
                <Input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="admin"
                  autoComplete="username"
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            <Field label="Mot de passe">
              <div className="relative">
                <LockKeyhole
                  size={16}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sand-500"
                />
                <Input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="pl-10"
                  required
                />
              </div>
            </Field>

            {error && <ErrorBanner message={error} />}

            <Button type="submit" loading={busy} className="w-full">
              Entrer dans le jeu
              <ArrowRight size={15} />
            </Button>

            <p className="text-center text-[0.7rem] leading-relaxed text-sand-500">
              Le mot de passe est transmis uniquement au backend, qui l’échange contre un
              jeton Emby. Il n’est jamais enregistré.
            </p>
          </form>
        )}

        <div className="mt-6 border-t border-cream-100/10 pt-4 text-center">
          <Link
            to="/setup"
            className="text-[0.7rem] uppercase tracking-[0.18em] text-sand-500 transition-colors hover:text-gold-300"
          >
            Configuration du serveur
          </Link>
        </div>
      </Card>
    </section>
  )
}
