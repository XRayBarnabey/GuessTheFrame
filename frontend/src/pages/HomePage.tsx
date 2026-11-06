import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  Award,
  CalendarDays,
  Clapperboard,
  Film,
  Layers,
  LibraryBig,
  Play,
  Shield,
  Sparkles,
  Swords,
  Tv,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'
import type { CatalogueSummary } from '../lib/types'
import { Button, Card, InfoBanner, PageLoader, Stat } from '../components/ui'
import { SectionTitle } from '../components/Logo'

export function HomePage() {
  const { user } = useAuth()
  const summaryQuery = useQuery({
    queryKey: ['catalogue-summary'],
    queryFn: () => api.get<CatalogueSummary>('/api/catalogue/summary'),
  })

  if (summaryQuery.isLoading) return <PageLoader />
  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <InfoBanner>
          Impossible de charger le catalogue. Vérifiez que le backend est démarré, puis
          rechargez la page.
        </InfoBanner>
      </section>
    )
  }

  const data = summaryQuery.data
  const winRate = data.user_stats.games
    ? Math.round((data.user_stats.won / data.user_stats.games) * 100)
    : 0
  const hasMedia = data.media.total > 0

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <section className="relative overflow-hidden border border-cream-100/[0.07] bg-ink-900/40 px-6 py-10 sm:px-10 sm:py-14">
        <div
          className="pointer-events-none absolute -right-20 -top-32 h-80 w-80 rounded-full bg-gold-400/10 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative grid gap-10 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
          <div className="animate-rise">
            <span className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-gold-400">
              {data.user_stats.games === 0 ? 'Première partie' : 'Bon retour'}
            </span>
            <h1 className="mt-4 font-display text-6xl leading-[0.92] tracking-[0.02em] text-cream-50 sm:text-7xl">
              {user?.username.toUpperCase()},
              <br />
              <span className="text-gold-400">DEVINEZ LA SUITE.</span>
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-relaxed text-sand-400 sm:text-base">
              Une vraie image extraite de votre bibliothèque Emby. Un film ou un épisode.
              À vous de trouver lequel avant de demander trop d’indices.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              {hasMedia ? (
                <Link to="/play">
                  <Button className="h-12 px-7">
                    <Play size={16} />
                    Nouvelle partie
                  </Button>
                </Link>
              ) : (
                <Button disabled className="h-12 px-7">
                  <Play size={16} />
                  Nouvelle partie
                </Button>
              )}
              <Link to="/daily">
                <Button variant="secondary" className="h-12 px-6">
                  <CalendarDays size={16} />
                  Film du jour
                </Button>
              </Link>
              <Link to="/duel">
                <Button variant="secondary" className="h-12 px-6">
                  <Swords size={16} />
                  Duel 1v1
                </Button>
              </Link>
              {user?.is_admin && (
                <Link to="/admin">
                  <Button variant="secondary" className="h-12 px-6">
                    <Shield size={15} />
                    Administration
                  </Button>
                </Link>
              )}
            </div>

            {!hasMedia && (
              <div className="mt-6 max-w-xl">
                <InfoBanner>
                  Aucun média n’est encore disponible. {user?.is_admin
                    ? 'Ouvrez l’administration pour lancer la synchronisation Emby.'
                    : 'Demandez à un administrateur de synchroniser le catalogue.'}
                </InfoBanner>
              </div>
            )}
          </div>

          <div className="animate-rise-delay grid grid-cols-2 gap-3">
            <Stat label="Médias" value={data.media.total} hint="films et épisodes" />
            <Stat label="Genres" value={data.genres.length} hint="disponibles" />
            <Stat
              label="Parties"
              value={data.user_stats.games}
              hint={`${data.user_stats.won} réussie(s)`}
            />
            <Stat
              label="Réussite"
              value={`${winRate}%`}
              hint="sur vos parties terminées"
            />
          </div>
        </div>
      </section>

      <section className="mt-12">
        <SectionTitle
          eyebrow="Votre catalogue"
          title="Ce qui peut tomber."
          description="Les filtres de partie utiliseront uniquement ces médias, issus de vos bibliothèques Emby autorisées."
        />
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="flex items-center gap-4 p-5">
            <span className="grid h-11 w-11 place-items-center border border-gold-400/20 bg-gold-400/[0.06] text-gold-300">
              <Film size={19} />
            </span>
            <div>
              <div className="font-display text-3xl leading-none text-cream-50">
                {data.media.movies}
              </div>
              <div className="mt-1 text-[0.65rem] uppercase tracking-[0.18em] text-sand-500">
                Films
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-4 p-5">
            <span className="grid h-11 w-11 place-items-center border border-gold-400/20 bg-gold-400/[0.06] text-gold-300">
              <Tv size={19} />
            </span>
            <div>
              <div className="font-display text-3xl leading-none text-cream-50">
                {data.media.episodes}
              </div>
              <div className="mt-1 text-[0.65rem] uppercase tracking-[0.18em] text-sand-500">
                Épisodes
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-4 p-5">
            <span className="grid h-11 w-11 place-items-center border border-gold-400/20 bg-gold-400/[0.06] text-gold-300">
              <LibraryBig size={19} />
            </span>
            <div>
              <div className="font-display text-3xl leading-none text-cream-50">
                {data.libraries.length}
              </div>
              <div className="mt-1 text-[0.65rem] uppercase tracking-[0.18em] text-sand-500">
                Bibliothèques
              </div>
            </div>
          </Card>
          <Card className="flex items-center gap-4 p-5">
            <span className="grid h-11 w-11 place-items-center border border-gold-400/20 bg-gold-400/[0.06] text-gold-300">
              <Layers size={19} />
            </span>
            <div>
              <div className="font-display text-3xl leading-none text-cream-50">
                {data.genres.length}
              </div>
              <div className="mt-1 text-[0.65rem] uppercase tracking-[0.18em] text-sand-500">
                Genres
              </div>
            </div>
          </Card>
        </div>
      </section>

      <section className="mt-12 grid gap-4 lg:grid-cols-3">
        <Card className="p-6">
          <Clapperboard size={20} className="text-gold-400" />
          <h3 className="mt-4 font-display text-2xl tracking-wide text-cream-50">
            Une frame, pas une affiche
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-sand-400">
            L’image est extraite de la vidéo elle-même. Aucune jaquette, aucun visuel
            promotionnel.
          </p>
        </Card>
        <Card className="p-6">
          <Sparkles size={20} className="text-gold-400" />
          <h3 className="mt-4 font-display text-2xl tracking-wide text-cream-50">
            Des indices à la demande
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-sand-400">
            Date de sortie, réalisateur, acteurs, et pour les séries le nom de l’épisode.
            Chaque indice réduit le score potentiel.
          </p>
        </Card>
        <Card className="p-6">
          <Award size={20} className="text-gold-400" />
          <h3 className="mt-4 font-display text-2xl tracking-wide text-cream-50">
            Un classement entre joueurs
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-sand-400">
            Vos statistiques et le leaderboard reposent sur vos comptes Emby, pas sur
            l’historique de lecture du serveur.
          </p>
        </Card>
      </section>

      {data.user_stats.games > 0 && (
        <section className="mt-12">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <SectionTitle eyebrow="Votre parcours" title="Vos performances." />
            <Link
              to="/profile"
              className="inline-flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-sand-400 transition-colors hover:text-gold-300"
            >
              Voir le profil
              <ArrowRight size={14} />
            </Link>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <Stat label="Parties jouées" value={data.user_stats.games} />
            <Stat label="Bonnes réponses" value={data.user_stats.won} />
            <Stat label="Score cumulé" value={data.user_stats.score} />
          </div>
        </section>
      )}
    </div>
  )
}
