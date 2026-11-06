import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Save } from 'lucide-react'
import { api, errorMessage } from '../lib/api'
import type { AdminSettings, DifficultyConfig, GameConfig, HintConfig } from '../lib/types'
import { Button, Card, ErrorBanner } from './ui'
import { Checkbox, Switch, inputClassSm } from './form'

const HINT_LABELS: Record<string, string> = {
  release_date: 'Date de sortie',
  director: 'Réalisateur',
  actor1: 'Acteur principal',
  actor2: 'Second acteur',
  character: 'Personnage principal',
  studio: 'Studio',
  media_type: 'Type de contenu',
  franchise: 'Saga / nombre de films ou saisons',
  episode_title: "Nom de l'épisode",
}

function NumberInput({
  label,
  value,
  onChange,
  min = 0,
  max = 9999,
  step = 1,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[0.62rem] uppercase tracking-[0.16em] text-sand-500">{label}</span>
      <input
        type="number"
        className={inputClassSm}
        value={Number.isFinite(value) ? value : 0}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

export function AdminSettingsForm({ settings }: { settings: AdminSettings }) {
  const queryClient = useQueryClient()
  const [game, setGame] = useState<GameConfig>({ ...settings.game_config })
  const [hints, setHints] = useState<HintConfig>({
    order: [...settings.hint_config.order],
    items: Object.fromEntries(
      Object.entries(settings.hint_config.items).map(([key, value]) => [key, { ...value }]),
    ),
  })
  const [difficulty, setDifficulty] = useState<DifficultyConfig>({
    easy: { ...settings.difficulty_config.easy },
    normal: { ...settings.difficulty_config.normal },
    hard: { ...settings.difficulty_config.hard },
  })
  const [syncEnabled, setSyncEnabled] = useState(settings.sync_enabled)
  const [saved, setSaved] = useState(false)

  const saveMutation = useMutation({
    mutationFn: () =>
      api.put('/api/admin/settings', {
        sync_enabled: syncEnabled,
        game_config: game,
        hint_config: hints,
        difficulty_config: difficulty,
      }),
    onSuccess: () => {
      setSaved(true)
      void queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['game-options'] })
      window.setTimeout(() => setSaved(false), 3000)
    },
  })

  function updateHint(key: string, patch: Partial<HintConfig['items'][string]>) {
    setHints((current) => ({
      ...current,
      items: {
        ...current.items,
        [key]: { ...current.items[key], ...patch },
      },
    }))
  }

  return (
    <Card className="mt-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-gold-400">
            Paramètres du jeu
          </div>
          <h2 className="mt-2 font-display text-3xl tracking-wide text-cream-50">
            Barème, indices et difficulté
          </h2>
        </div>
        <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
          <Save size={15} />
          Enregistrer
        </Button>
      </div>

      {saveMutation.isError && (
        <div className="mt-4">
          <ErrorBanner message={errorMessage(saveMutation.error)} />
        </div>
      )}
      {saved && (
        <div className="mt-4 flex items-center gap-2 border border-success-400/25 bg-success-400/[0.06] px-4 py-3 text-sm text-success-400">
          <CheckCircle2 size={16} />
          Paramètres enregistrés.
        </div>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <NumberInput
          label="Score de base"
          value={game.base_points}
          min={0}
          max={1000}
          onChange={(value) => setGame({ ...game, base_points: value })}
        />
        <NumberInput
          label="Pénalité par erreur"
          value={game.wrong_attempt_penalty}
          min={0}
          max={100}
          onChange={(value) => setGame({ ...game, wrong_attempt_penalty: value })}
        />
        <NumberInput
          label="Pénalité erreurs max."
          value={game.max_wrong_penalty}
          min={0}
          max={500}
          onChange={(value) => setGame({ ...game, max_wrong_penalty: value })}
        />
        <NumberInput
          label="Largeur des frames (px)"
          value={game.frame_width}
          min={320}
          max={3840}
          step={10}
          onChange={(value) => setGame({ ...game, frame_width: value })}
        />
        <NumberInput
          label="Tentatives max. (0 = illimité)"
          value={game.max_attempts}
          min={0}
          max={100}
          onChange={(value) => setGame({ ...game, max_attempts: value })}
        />
        <NumberInput
          label="Tolérance de saisie (%)"
          value={game.answer_similarity}
          min={70}
          max={100}
          onChange={(value) => setGame({ ...game, answer_similarity: value })}
        />
        <NumberInput
          label="Abandon auto. après inactivité (min)"
          value={game.game_inactivity_minutes}
          min={5}
          max={1440}
          onChange={(value) => setGame({ ...game, game_inactivity_minutes: value })}
        />
        <NumberInput
          label="Duel 1v1 : pénalité par indice (s)"
          value={game.duel_hint_penalty_seconds}
          min={0}
          max={300}
          onChange={(value) => setGame({ ...game, duel_hint_penalty_seconds: value })}
        />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Checkbox
          label="Accepter le nom de la série seul comme réponse"
          checked={game.accept_series_name}
          onChange={(checked) => setGame({ ...game, accept_series_name: checked })}
        />
        <Checkbox
          label="Autoriser les joueurs à filtrer par bibliothèque"
          checked={game.allow_library_filter}
          onChange={(checked) => setGame({ ...game, allow_library_filter: checked })}
        />
        <Checkbox
          label="Exclure les médias déjà devinés par défaut"
          checked={game.exclude_solved_default}
          onChange={(checked) => setGame({ ...game, exclude_solved_default: checked })}
        />
        <Checkbox
          label="Synchronisation automatique activée"
          checked={syncEnabled}
          onChange={setSyncEnabled}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
            Indices disponibles
          </div>
          <div className="mt-3 space-y-2">
            {Object.keys(HINT_LABELS).map((key) => {
              const item = hints.items[key] ?? { enabled: false, penalty: 0 }
              return (
                <div
                  key={key}
                  className="flex items-center justify-between gap-3 border border-cream-100/[0.07] bg-ink-950/40 px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <Switch
                      label={`Activer ${HINT_LABELS[key]}`}
                      checked={item.enabled}
                      onChange={(enabled) => updateHint(key, { enabled })}
                    />
                    <span className="text-sm text-cream-100">{HINT_LABELS[key]}</span>
                  </div>
                  <label className="flex items-center gap-2 text-[0.65rem] text-sand-500">
                    −
                    <input
                      type="number"
                      className="h-8 w-16 border border-cream-100/12 bg-ink-950/60 px-2 text-right text-sm text-cream-100 outline-none focus:border-gold-400/60"
                      value={item.penalty}
                      min={0}
                      max={100}
                      onChange={(event) =>
                        updateHint(key, { penalty: Number(event.target.value) })
                      }
                    />
                    pts
                  </label>
                </div>
              )
            })}
          </div>
          <p className="mt-2 text-[0.65rem] leading-relaxed text-sand-500">
            L’ordre est fixe. Les joueurs peuvent choisir librement l’indice qu’ils
            souhaitent révéler. Un indice absent des métadonnées Emby est ignoré.
          </p>
        </div>

        <div>
          <div className="text-[0.62rem] uppercase tracking-[0.18em] text-sand-500">
            Difficultés
          </div>
          <div className="mt-3 space-y-2">
            {(['easy', 'normal', 'hard'] as const).map((key) => {
              const item = difficulty[key]
              const labels = { easy: 'Facile', normal: 'Normale', hard: 'Difficile' }
              return (
                <div key={key} className="border border-cream-100/[0.07] bg-ink-950/40 p-3">
                  <div className="text-xs font-semibold text-cream-100">{labels[key]}</div>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    <NumberInput
                      label="Indices"
                      value={item.max_hints}
                      min={0}
                      max={10}
                      onChange={(value) =>
                        setDifficulty({
                          ...difficulty,
                          [key]: { ...item, max_hints: value },
                        })
                      }
                    />
                    <NumberInput
                      label="Pénalité ×"
                      value={item.wrong_penalty_multiplier}
                      min={0}
                      max={5}
                      step={0.1}
                      onChange={(value) =>
                        setDifficulty({
                          ...difficulty,
                          [key]: { ...item, wrong_penalty_multiplier: value },
                        })
                      }
                    />
                    <NumberInput
                      label="Score ×"
                      value={item.score_multiplier}
                      min={0}
                      max={5}
                      step={0.1}
                      onChange={(value) =>
                        setDifficulty({
                          ...difficulty,
                          [key]: { ...item, score_multiplier: value },
                        })
                      }
                    />
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 border border-cream-100/10 bg-ink-950/40 px-3 py-2 text-xs leading-relaxed text-sand-400">
            Le catalogue est actualisé automatiquement <strong className="text-cream-100">tous les jours à 12:00</strong>{' '}
            (heure de Paris) lorsque la synchronisation automatique est activée.
          </div>
        </div>
      </div>
    </Card>
  )
}
