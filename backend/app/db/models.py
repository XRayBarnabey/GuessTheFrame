"""Database models for GuessTheFrame."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


def new_uuid() -> str:
    return str(uuid4())


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("emby_server_id", "emby_user_id", name="uq_users_server_emby"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emby_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    emby_server_id: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    username_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_in_leaderboard: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    showcase_media_ids: Mapped[list[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    games: Mapped[list["Game"]] = relationship(back_populates="user")


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    emby_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    emby_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    emby_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    emby_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    emby_server_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emby_server_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emby_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emby_verify_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    game_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hint_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    difficulty_config: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Library(Base, TimestampMixin):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emby_library_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MediaItem(Base, TimestampMixin):
    __tablename__ = "media_items"
    __table_args__ = (
        UniqueConstraint("emby_server_id", "emby_item_id", name="uq_media_server_emby"),
        Index("ix_media_type_active", "type", "is_active"),
        Index("ix_media_library", "library_id"),
        Index("ix_media_series", "series_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    emby_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    emby_server_id: Mapped[str] = mapped_column(String(64), nullable=False)
    library_id: Mapped[int | None] = mapped_column(
        ForeignKey("libraries.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # movie|episode
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_ticks: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    official_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    community_rating: Mapped[float | None] = mapped_column(Float, nullable=True)

    series_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    series_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    series_original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    premiere_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    people: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    studios: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    collections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    chapters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    media_sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    search_text: Mapped[str] = mapped_column(String(1024), default="", nullable=False)

    media_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container: Mapped[str | None] = mapped_column(String(32), nullable=True)
    video_range: Mapped[str | None] = mapped_column(String(32), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    poster_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    backdrop_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    emby_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    library: Mapped[Library | None] = relationship()
    genre_links: Mapped[list["MediaGenre"]] = relationship(
        back_populates="media", cascade="all, delete-orphan"
    )


class Genre(Base):
    __tablename__ = "genres"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MediaGenre(Base):
    __tablename__ = "media_genres"
    __table_args__ = (Index("ix_media_genres_genre", "genre"),)

    media_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True
    )
    genre: Mapped[str] = mapped_column(String(128), primary_key=True)

    media: Mapped[MediaItem] = relationship(back_populates="genre_links")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        Index("ix_games_user_finished", "user_id", "finished_at"),
        Index("ix_games_status", "status"),
        UniqueConstraint("user_id", "daily_date", name="uq_games_user_daily_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="in_progress", nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="classic", nullable=False)
    ranking_category: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )
    daily_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hints_used: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frame_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    media_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="games")
    media: Mapped[MediaItem] = relationship()
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    hints: Mapped[list["Hint"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_game", "game_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    guess: Mapped[str] = mapped_column(String(512), nullable=False)
    guess_norm: Mapped[str] = mapped_column(String(512), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    game: Mapped[Game] = relationship(back_populates="attempts")


class Hint(Base):
    __tablename__ = "hints"
    __table_args__ = (Index("ix_hints_game", "game_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    hint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    penalty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    game: Mapped[Game] = relationship(back_populates="hints")


class FrameCache(Base):
    __tablename__ = "frame_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DailyChallenge(Base):
    __tablename__ = "daily_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_date: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DuelMatch(Base, TimestampMixin):
    __tablename__ = "duel_matches"
    __table_args__ = (
        Index("ix_duel_matches_status_phase", "status", "phase"),
        Index("ix_duel_matches_players", "player1_id", "player2_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False)
    phase: Mapped[str] = mapped_column(String(16), default="lobby", nullable=False)
    player1_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    player2_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    settings_setter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    winner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    exchange_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    last_dice: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    participants: Mapped[list["DuelParticipant"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    frames: Mapped[list["DuelFrame"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class DuelParticipant(Base, TimestampMixin):
    __tablename__ = "duel_participants"
    __table_args__ = (
        UniqueConstraint("match_id", "user_id", name="uq_duel_participant_user"),
        UniqueConstraint("match_id", "seat", name="uq_duel_participant_seat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("duel_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    dice_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dice_history: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    selected_frame_ids: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    submitted_exchange: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    found_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hints_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_penalty_seconds: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    match: Mapped[DuelMatch] = relationship(back_populates="participants")


class DuelFrame(Base, TimestampMixin):
    __tablename__ = "duel_frames"
    __table_args__ = (
        UniqueConstraint(
            "match_id", "original_owner_id", "position", name="uq_duel_frame_slot"
        ),
        Index("ix_duel_frames_holder", "match_id", "holder_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("duel_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    holder_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media_items.id", ondelete="RESTRICT"), nullable=False
    )
    media_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    frame_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    frame_cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="classic", nullable=False)
    solved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    solved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    match: Mapped[DuelMatch] = relationship(back_populates="frames")


class DuelHint(Base):
    __tablename__ = "duel_hints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("duel_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_id: Mapped[str] = mapped_column(
        ForeignKey("duel_frames.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    hint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DuelGuess(Base):
    __tablename__ = "duel_guesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        ForeignKey("duel_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_id: Mapped[str] = mapped_column(
        ForeignKey("duel_frames.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    guess: Mapped[str] = mapped_column(String(512), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    libraries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deactivated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
