import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LogOut, Shield, Home, Trophy, UserRound, Moon, Sun, Swords } from 'lucide-react'
import clsx from 'clsx'
import { Logo } from './Logo'
import { Badge } from './ui'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'
import type { Health } from '../lib/types'
import { useTheme } from '../lib/theme'

export function AppShell() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<Health>('/api/health'),
    staleTime: 60_000,
  })
  const sourceName = healthQuery.data?.emby.name ?? 'Emby'

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="grain vignette flex min-h-svh flex-col">
      <div className="spotlight pointer-events-none fixed inset-0" aria-hidden="true" />
      <header className="relative z-30 border-b border-cream-100/[0.07] bg-ink-950/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Logo />
          <nav className="flex items-center gap-1 sm:gap-2">
            {user ? (
              <>
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) =>
                    clsx(
                      'hidden items-center gap-2 px-3 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors sm:inline-flex',
                      isActive
                        ? 'text-gold-300'
                        : 'text-sand-400 hover:text-cream-100',
                    )
                  }
                >
                  <Home size={14} />
                  Accueil
                </NavLink>
                {user.is_admin && (
                  <NavLink
                    to="/admin"
                    className={({ isActive }) =>
                      clsx(
                        'inline-flex items-center gap-2 px-3 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors',
                        isActive
                          ? 'text-gold-300'
                          : 'text-sand-400 hover:text-cream-100',
                      )
                    }
                  >
                    <Shield size={14} />
                    <span className="hidden lg:inline">Administration</span>
                  </NavLink>
                )}
                <NavLink
                  to="/leaderboard"
                  className={({ isActive }) =>
                    clsx(
                      'inline-flex items-center gap-2 px-2 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors sm:px-3',
                      isActive ? 'text-gold-300' : 'text-sand-400 hover:text-cream-100',
                    )
                  }
                  title="Classement"
                >
                  <Trophy size={14} />
                  <span className="hidden xl:inline">Classement</span>
                </NavLink>
                <NavLink
                  to="/duel"
                  className={({ isActive }) =>
                    clsx(
                      'inline-flex items-center gap-2 px-2 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors sm:px-3',
                      isActive ? 'text-gold-300' : 'text-sand-400 hover:text-cream-100',
                    )
                  }
                  title="Duel 1v1"
                >
                  <Swords size={14} />
                  <span className="hidden xl:inline">Duel</span>
                </NavLink>
                <NavLink
                  to="/profile"
                  className={({ isActive }) =>
                    clsx(
                      'inline-flex items-center gap-2 px-2 py-2 text-[0.66rem] font-semibold uppercase tracking-[0.18em] transition-colors sm:px-3',
                      isActive ? 'text-gold-300' : 'text-sand-400 hover:text-cream-100',
                    )
                  }
                  title="Profil"
                >
                  <UserRound size={14} />
                  <span className="hidden xl:inline">Profil</span>
                </NavLink>
                <div className="mx-1 hidden h-5 w-px bg-cream-100/10 sm:block" />
                <NavLink
                  to="/profile"
                  className="hidden max-w-[11rem] items-center gap-2 text-xs text-sand-400 transition-colors hover:text-cream-100 sm:flex"
                  title="Voir mon profil"
                >
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt=""
                      className="h-7 w-7 shrink-0 border border-cream-100/15 object-cover"
                    />
                  ) : (
                    <span className="grid h-7 w-7 shrink-0 place-items-center border border-cream-100/15 bg-ink-900 font-display text-xs text-gold-300">
                      {(user.display_name ?? user.username).slice(0, 2).toUpperCase()}
                    </span>
                  )}
                  <span className="truncate">{user.display_name ?? user.username}</span>
                </NavLink>
                <button
                  type="button"
                  onClick={toggle}
                  className="grid h-9 w-9 place-items-center text-sand-500 transition-colors hover:text-gold-300"
                  title={theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'}
                  aria-label={theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'}
                >
                  {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                </button>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="grid h-9 w-9 place-items-center text-sand-500 transition-colors hover:text-danger-400"
                  title="Se déconnecter"
                  aria-label="Se déconnecter"
                >
                  <LogOut size={16} />
                </button>
              </>
            ) : (
              <>
                <Badge tone="gold">Emby</Badge>
                <button
                  type="button"
                  onClick={toggle}
                  className="grid h-9 w-9 place-items-center text-sand-500 transition-colors hover:text-gold-300"
                  title={theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'}
                  aria-label={theme === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre'}
                >
                  {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                </button>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="relative z-10 flex-1">
        <Outlet />
      </main>

      <footer className="relative z-10 border-t border-cream-100/[0.06] px-4 py-6">
        <div className="mx-auto flex w-full max-w-7xl justify-center text-center text-[0.72rem] tracking-[0.08em] text-sand-500">
          <span>Source de la base : {sourceName}</span>
        </div>
      </footer>
    </div>
  )
}
