export type Health = {
  status: 'ok' | 'degraded'
  app: string
  version: string
  environment: string
  database: 'ok' | 'error'
  emby: {
    url: string
    name: string | null
    configured: boolean
  }
}

export type User = {
  id: number
  emby_user_id: string
  username: string
  display_name: string | null
  avatar_url: string | null
  is_admin: boolean
  is_active: boolean
  show_in_leaderboard: boolean
  last_login_at: string | null
}

export type AuthResponse = {
  user: User
  csrf_token: string
}

export type SetupLibrary = {
  id: string
  name: string
  collection_type: string | null
  item_count: number
  enabled: boolean
}

export type SetupStatus = {
  setup_complete: boolean
  secrets_ready: boolean
  setup_token_required: boolean
  emby_url: string
  server_name: string | null
  server_version: string | null
  libraries: SetupLibrary[]
  ffmpeg: {
    available: boolean
    path: string
  }
}

export type CatalogueSummary = {
  media: {
    total: number
    movies: number
    episodes: number
  }
  libraries: {
    id: string
    name: string
    collection_type: string | null
  }[]
  genres: {
    name: string
    media_count: number
  }[]
  user_stats: {
    games: number
    won: number
    score: number
  }
}

export type SyncRun = {
  id: number
  mode: string
  status: 'running' | 'success' | 'failed'
  started_at: string
  finished_at: string | null
  libraries: number
  items_seen: number
  added: number
  updated: number
  deactivated: number
  errors: number
  error_message: string | null
}

export type SyncStatus = {
  running: boolean
  last_sync_at: string | null
  sync_enabled: boolean
  sync_interval_minutes: number
  last_run: SyncRun | null
  catalogue: {
    media: number
    movies: number
    episodes: number
  }
}

export type AdminLibrary = {
  id: string
  name: string
  collection_type: string | null
  is_enabled: boolean
  item_count: number
  last_synced_at: string | null
}

export type AdminGenre = {
  name: string
  is_enabled: boolean
  media_count: number
}

export type AdminOverview = {
  users: number
  games: number
  won: number
  setup_complete: boolean
  emby: {
    url: string
    server_name: string | null
    version: string | null
  }
}

export type GameConfig = {
  base_points: number
  wrong_attempt_penalty: number
  max_wrong_penalty: number
  accept_series_name: boolean
  frame_width: number
  max_attempts: number
  answer_similarity: number
  allow_library_filter: boolean
  exclude_solved_default: boolean
  game_expiry_hours: number
  game_inactivity_minutes: number
  duel_hint_penalty_seconds: number
}

export type HintItemConfig = {
  enabled: boolean
  penalty: number
}

export type HintConfig = {
  order: string[]
  items: Record<string, HintItemConfig>
}

export type DifficultyItemConfig = {
  max_hints: number
  wrong_penalty_multiplier: number
  score_multiplier: number
}

export type DifficultyConfig = {
  easy: DifficultyItemConfig
  normal: DifficultyItemConfig
  hard: DifficultyItemConfig
}

export type AdminSettings = {
  emby_url: string
  emby_verify_tls: boolean
  emby_server_name: string | null
  emby_version: string | null
  emby_api_key_configured: boolean
  sync_enabled: boolean
  sync_interval_minutes: number
  last_sync_at: string | null
  game_config: GameConfig
  hint_config: HintConfig
  difficulty_config: DifficultyConfig
}

export type CacheStatus = {
  path: string
  files: number
  bytes: number
  megabytes: number
  max_megabytes: number
  db_entries: number
}

export type AdminUser = {
  id: number
  username: string
  emby_user_id: string
  is_admin: boolean
  is_active: boolean
  games: number
  last_login_at: string | null
}

export type AdminUsersResponse = {
  users: AdminUser[]
}

export type GameOptions = {
  types: { value: 'movie' | 'episode'; label: string; count: number }[]
  genres: { name: string; media_count: number }[]
  libraries: {
    id: string
    name: string
    collection_type: string | null
    media_count: number
  }[]
  difficulties: {
    key: 'easy' | 'normal' | 'hard'
    max_hints: number
    score_multiplier: number
  }[]
  defaults: {
    media_types: ('movie' | 'episode')[]
    difficulty: 'easy' | 'normal' | 'hard'
    exclude_solved: boolean
    allow_library_filter: boolean
  }
  excluded_solved: number
  min_runtime_seconds: number
}

export type GameFilters = {
  media_types: ('movie' | 'episode')[]
  genres: string[]
  library_ids: string[] | null
  exclude_solved: boolean
  mode?: string
  date?: string
}

export type Hint = {
  key: string
  label: string
  value: string
  penalty: number
}

export type HintOption = {
  key: string
  label: string
  penalty: number
  used: boolean
}

export type GameState = {
  id: string
  status: 'in_progress' | 'won' | 'abandoned' | 'expired'
  mode: 'classic' | 'frames3' | 'frames5' | 'dezoom' | 'daily'
  mode_label: string
  ranking_category: string | null
  difficulty: 'easy' | 'normal' | 'hard'
  attempts_count: number
  hints_used: Hint[]
  hint_options: HintOption[]
  score_potential: number
  score: number | null
  max_hints: number
  zoom_level: number
  frame_count: number
  frame_urls: string[]
  started_at: string
  last_activity_at: string | null
  expires_at: string | null
  inactivity_minutes: number
  finished_at: string | null
  frame_url: string
  has_frame: boolean
  filters: GameFilters
  daily_date: string | null
  hint?: Hint
  result?: GameResult
}

export type GameMediaResult = {
  type: 'movie' | 'episode'
  title: string | null
  original_title: string | null
  answer_label: string
  display_title: string
  year: number | null
  overview: string | null
  genres: string[]
  directors: string[]
  actors: string[]
  runtime_minutes: number | null
  poster_url: string | null
  emby_url: string | null
  series_name: string | null
  series_original_title: string | null
  season_number: number | null
  episode_number: number | null
  episode_title: string | null
}

export type GameResult = {
  game_id: string
  status: 'won' | 'abandoned' | 'expired'
  won: boolean
  score: number
  attempts_count: number
  duration_seconds: number | null
  hints_used: Hint[]
  score_breakdown: Record<string, unknown>
  finished_at: string | null
  emby_server_name: string | null
  media: GameMediaResult
}

export type AttemptResponse = {
  correct: boolean
  attempts_count: number
  state: GameState
  result?: GameResult
}

export type LeaderboardEntry = {
  rank: number
  user_id: number
  username: string
  wins: number
  games: number
  win_rate: number
  score: number
}

export type Leaderboard = {
  period: 'all' | 'week' | 'month'
  category?: 'general' | 'movies' | 'series' | 'duel'
  entries: LeaderboardEntry[]
}

export type ProfileStats = {
  games: number
  wins: number
  win_rate: number
  score: number
  best_score: number
  avg_attempts: number
  avg_duration_seconds: number
  show_in_leaderboard: boolean
}

export type ShowcaseItem = {
  media_id: number
  title: string
  kind: 'movie' | 'series' | 'anime'
  year: number | null
  subtitle: string | null
  poster_url: string | null
}

export type HistoryItem = {
  id: string
  status: 'won' | 'abandoned' | 'expired'
  score: number
  attempts_count: number
  duration_seconds: number | null
  finished_at: string | null
  media_type: 'movie' | 'episode'
  title: string | null
  subtitle: string | null
  year: number | null
  poster_url: string | null
}

export type HistoryPage = {
  page: number
  page_size: number
  total: number
  items: HistoryItem[]
}

export type TitleSuggestion = {
  title: string
  type: 'movie' | 'episode'
  year: number | null
}

export type TitleSuggestions = {
  items: TitleSuggestion[]
}

export type DuelMedia = {
  type: 'movie' | 'episode' | null
  title: string | null
  original_title: string | null
  answer_label: string | null
  display_title: string
  year: number | null
  series_name: string | null
  season_number: number | null
  episode_number: number | null
  episode_title: string | null
}

export type DuelFrameState = {
  id: string
  position: number
  solved: boolean
  image_url: string
  hint_options: HintOption[]
  hints_used: Hint[]
  media: DuelMedia | null
}

export type DuelParticipantState = {
  user_id: number
  username: string
  seat: number
  dice_value: number | null
  dice_history: number[]
  found: number
  attempts: number
  hints: number
  submitted_exchange: boolean
  finished: boolean
  deadline_at: string | null
  remaining_seconds: number | null
  timed_out: boolean
}

export type DuelPlayerResult = {
  user_id: number
  username: string
  seat: number
  found: number
  attempts: number
  hints: number
  time_penalty_seconds: number
  finished_at: string | null
  winner: boolean
}

export type DuelFrameHint = {
  user_id: number
  username: string
  key: string
  label: string
  value: string | null
  penalty: number
}

export type DuelResultFrame = {
  id: string
  original_owner_id: number
  original_owner_username: string
  holder_id: number
  holder_username: string
  exchanged: boolean
  position: number
  media: DuelMedia
  solved_by_user_id: number | null
  solved_by_username: string | null
  hints: DuelFrameHint[]
}

export type DuelResult = {
  winner_id: number | null
  winner_username: string | null
  draw: boolean
  reason: 'time' | 'completed' | 'early_end' | 'abandon' | 'cancelled' | string
  cancelled: boolean
  ranked: boolean
  players: DuelPlayerResult[]
  frames: DuelResultFrame[]
}

export type DuelProposal = {
  type: 'finish' | 'cancel'
  by: number
  created_at?: string
}

export type DuelState = {
  id: string
  code: string
  status: 'waiting' | 'active' | 'finished' | 'cancelled'
  phase: 'lobby' | 'dice' | 'settings' | 'exchange' | 'playing' | 'finished'
  server_time: string
  player1: { user_id: number; username: string }
  player2: { user_id: number | null; username: string | null }
  settings_setter_id: number | null
  winner_id: number | null
  exchange_count: number
  duration_seconds: number
  hint_penalty_seconds: number
  last_dice: {
    player1?: number
    player2?: number
    tie?: boolean
    winner_id?: number
  }
  proposal: DuelProposal | null
  started_at: string | null
  ends_at: string | null
  finished_at: string | null
  filters: {
    categories?: ('movie' | 'series' | 'anime')[]
    media_types: ('movie' | 'episode')[]
    genres: string[]
    library_ids: string[] | null
  }
  you: DuelParticipantState
  opponent: DuelParticipantState | null
  frames: DuelFrameState[]
  result: DuelResult | Record<string, never>
  hint?: Hint
}

export type DuelSummary = {
  id: string
  code: string
  phase: string
  status: string
  created_at: string | null
  player1_id: number
  player2_id: number | null
  winner_id: number | null
}
