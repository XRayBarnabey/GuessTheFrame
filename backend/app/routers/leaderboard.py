"""Leaderboard endpoints (all-time, weekly, monthly)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_session
from app.db.base import utcnow
from app.db.models import DuelMatch, Game, User, UserSession
from app.db.session import get_db

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("")
async def leaderboard(
    period: Literal["all", "week", "month"] = Query(default="all"),
    category: Literal["general", "movies", "series"] = Query(default="general"),
    limit: int = Query(default=50, ge=1, le=100),
    _: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    wins = func.sum(case((Game.status == "won", 1), else_=0))
    score = func.sum(case((Game.status == "won", Game.score), else_=0))

    base_filters = [
        User.is_active.is_(True),
        User.show_in_leaderboard.is_(True),
        Game.status.in_(["won", "abandoned", "expired"]),
        Game.ranking_category == category,
    ]
    now = utcnow()
    if period == "week":
        base_filters.append(Game.finished_at >= now - timedelta(days=7))
    elif period == "month":
        base_filters.append(Game.finished_at >= now - timedelta(days=30))

    statement = (
        select(
            User.id,
            func.coalesce(User.display_name, User.username).label("username"),
            func.count(Game.id).label("games"),
            wins.label("wins"),
            score.label("score"),
        )
        .join(Game, Game.user_id == User.id)
        .where(*base_filters)
        .group_by(User.id, func.coalesce(User.display_name, User.username))
        .order_by(desc("wins"), desc("score"), func.coalesce(User.display_name, User.username).asc())
        .limit(limit)
    )

    rows = (await db.execute(statement)).all()

    entries = []
    for rank, (user_id, username, games, won, total_score) in enumerate(rows, start=1):
        games = int(games or 0)
        won = int(won or 0)
        entries.append(
            {
                "rank": rank,
                "user_id": user_id,
                "username": username,
                "wins": won,
                "games": games,
                "win_rate": round((won / games) * 100, 1) if games else 0.0,
                "score": int(total_score or 0),
            }
        )

    return {"period": period, "category": category, "entries": entries}


@router.get("/duel")
async def duel_leaderboard(
    period: Literal["all", "week", "month"] = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=100),
    _: UserSession = Depends(require_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    now = utcnow()
    statement = select(DuelMatch).where(
        DuelMatch.status == "finished",
        DuelMatch.finished_at.is_not(None),
    )
    if period == "week":
        statement = statement.where(DuelMatch.finished_at >= now - timedelta(days=7))
    elif period == "month":
        statement = statement.where(DuelMatch.finished_at >= now - timedelta(days=30))
    matches = (await db.execute(statement)).scalars().all()

    stats: dict[int, dict[str, int]] = {}
    for match in matches:
        for user_id in (match.player1_id, match.player2_id):
            if not user_id:
                continue
            item = stats.setdefault(user_id, {"games": 0, "wins": 0})
            item["games"] += 1
            if match.winner_id == user_id:
                item["wins"] += 1

    if not stats:
        return {"period": period, "entries": []}

    users = (
        await db.execute(
            select(User).where(
                User.id.in_(list(stats)),
                User.is_active.is_(True),
                User.show_in_leaderboard.is_(True),
            )
        )
    ).scalars().all()

    entries = []
    for user in users:
        item = stats[user.id]
        games = item["games"]
        display_name = user.display_name or user.username
        entries.append(
            {
                "rank": 0,
                "user_id": user.id,
                "username": display_name,
                "wins": item["wins"],
                "games": games,
                "win_rate": round((item["wins"] / games) * 100, 1) if games else 0.0,
                "score": 0,
            }
        )
    entries.sort(
        key=lambda entry: (
            -entry["wins"],
            -entry["win_rate"],
            entry["username"].casefold(),
        )
    )
    entries = entries[:limit]
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return {"period": period, "entries": entries}
