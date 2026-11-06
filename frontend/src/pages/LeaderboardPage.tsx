import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Crown, Medal, Trophy } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import type { Leaderboard } from '../lib/types'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorBanner, PageLoader } from '../components/ui'
import { SectionTitle } from '../components/Logo'

type Period = 'all' | 'week' | 'month'
type Category = 'general' | 'movies' | 'series' | 'duel'

const PERIODS: { key: Period; label: string }[] = [
  { key: 'all', label: 'Général' },
  { key: 'week', label: '7 jours' },
  { key: 'month', label: '30 jours' },
]

const CATEGORIES: { key: Category; label: string; description: string }[] = [
  {
    key: 'general',
    label: 'Films + Séries',
    description: 'Parties avec tous les types de contenus et tous les genres.',
  },
  {
    key: 'movies',
    label: 'Films uniquement',
    description: 'Parties limitées aux films, avec tous les genres.',
  },
  {
    key: 'series',
    label: 'Séries uniquement',
    description: 'Parties limitées aux séries, avec tous les genres.',
  },
  {
    key: 'duel',
    label: 'Duels 1v1',
    description: 'Classement des duels 1v1 terminés.',
  },
]

export function LeaderboardPage() {
  const { user } = useAuth()
  const [period, setPeriod] = useState<Period>('all')
  const [category, setCategory] = useState<Category>('general')
  const leaderboardQuery = useQuery({
    queryKey: ['leaderboard', period, category],
    queryFn: () =>
      api.get<Leaderboard>(
        category === 'duel'
          ? `/api/leaderboard/duel?period=${period}`
          : `/api/leaderboard?period=${period}&category=${category}`,
      ),
  })

  if (leaderboardQuery.isLoading) return <PageLoader />
  if (leaderboardQuery.isError || !leaderboardQuery.data) {
    return (
      <section className="mx-auto w-full max-w-4xl px-4 py-16">
        <ErrorBanner message="Impossible de charger le classement." />
      </section>
    )
  }

  const entries = leaderboardQuery.data.entries
  const isDuel = category === 'duel'

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <SectionTitle
          eyebrow="Classement"
          title={isDuel ? 'Les meilleurs duellistes.' : 'Les meilleurs enquêteurs.'}
          description={
            isDuel
              ? 'Le classement 1v1 repose sur les victoires, puis sur le taux de victoire.'
              : 'Le classement principal repose sur le nombre de bonnes réponses. Les scores cumulés départagent les égalités.'
          }
        />
        <Link to="/">
          <Button variant="ghost">
            <ArrowLeft size={14} />
            Accueil
          </Button>
        </Link>
      </div>

      <div className="mt-7 flex flex-wrap gap-2">
        {CATEGORIES.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setCategory(item.key)}
            className={clsx(
              'border px-4 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors',
              category === item.key
                ? 'border-gold-400/60 bg-gold-400/10 text-gold-300'
                : 'border-cream-100/10 bg-ink-900/40 text-sand-400 hover:border-cream-100/25 hover:text-cream-100',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <p className="mt-3 text-xs leading-relaxed text-sand-500">
        {CATEGORIES.find((item) => item.key === category)?.description}{' '}
        {isDuel
          ? 'Seuls les duels terminés sont pris en compte.'
          : 'Les parties journalières et les parties avec filtres personnalisés (genres ou bibliothèques) ne sont pas comptabilisées dans les classements solo.'}
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        {PERIODS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setPeriod(item.key)}
            className={clsx(
              'border px-4 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors',
              period === item.key
                ? 'border-gold-400/60 bg-gold-400/10 text-gold-300'
                : 'border-cream-100/10 bg-ink-900/40 text-sand-400 hover:border-cream-100/25 hover:text-cream-100',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <Card className="mt-6 overflow-hidden">
        {entries.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <Trophy size={30} className="mx-auto text-sand-500" />
            <p className="mt-4 text-sm text-sand-400">
              {isDuel
                ? 'Aucun duel terminé sur cette période. Soyez les premiers à entrer au classement.'
                : 'Aucune partie terminée dans cette catégorie sur cette période. Soyez le premier à entrer au classement.'}
            </p>
            <Link to={isDuel ? '/duel' : '/play'} className="mt-5 inline-block">
              <Button>{isDuel ? 'Lancer un duel' : 'Lancer une partie'}</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[38rem] border-collapse text-left">
              <thead>
                <tr className="border-b border-cream-100/10 text-[0.6rem] uppercase tracking-[0.18em] text-sand-500">
                  <th className="px-4 py-3 font-medium sm:px-6">Position</th>
                  <th className="px-4 py-3 font-medium">Joueur</th>
                  <th className="px-4 py-3 text-right font-medium">
                    {isDuel ? 'Victoires' : 'Réussies'}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {isDuel ? 'Duels' : 'Parties'}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {isDuel ? 'Taux de victoire' : 'Réussite'}
                  </th>
                  {!isDuel && (
                    <th className="px-4 py-3 text-right font-medium">Score</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const isMe = entry.username === user?.username
                  return (
                    <tr
                      key={entry.user_id}
                      className={clsx(
                        'border-b border-cream-100/[0.05] text-sm last:border-0',
                        isMe ? 'bg-gold-400/[0.06]' : 'hover:bg-cream-100/[0.02]',
                      )}
                    >
                      <td className="px-4 py-3 sm:px-6">
                        <div className="flex items-center gap-2">
                          {entry.rank === 1 ? (
                            <Crown size={16} className="text-gold-300" />
                          ) : entry.rank === 2 || entry.rank === 3 ? (
                            <Medal size={15} className="text-sand-400" />
                          ) : null}
                          <span
                            className={clsx(
                              'font-display text-xl',
                              entry.rank === 1 ? 'text-gold-300' : 'text-sand-400',
                            )}
                          >
                            {entry.rank}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={clsx('font-medium', isMe ? 'text-gold-200' : 'text-cream-100')}>
                            {entry.username}
                          </span>
                          {isMe && (
                            <span className="border border-gold-400/30 px-1.5 py-0.5 text-[0.55rem] uppercase tracking-[0.14em] text-gold-400">
                              Vous
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-display text-lg text-cream-100">
                        {entry.wins}
                      </td>
                      <td className="px-4 py-3 text-right text-sand-400">{entry.games}</td>
                      <td className="px-4 py-3 text-right text-sand-400">{entry.win_rate}%</td>
                      {category !== 'duel' && (
                        <td className="px-4 py-3 text-right font-medium text-gold-300">
                          {entry.score}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="mt-4 text-[0.7rem] leading-relaxed text-sand-500">
        {isDuel
          ? 'Seuls les utilisateurs Emby actifs ayant terminé au moins un duel apparaissent. Les duels nuls comptent dans le total, pas dans les victoires.'
          : 'Seuls les utilisateurs Emby actifs ayant terminé au moins une partie apparaissent. Les parties abandonnées comptent dans le total et le taux de réussite, pas dans les bonnes réponses.'}
      </p>
    </div>
  )
}
