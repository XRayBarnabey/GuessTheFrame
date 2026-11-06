"""Emby catalogue synchronisation.

The sync is intentionally non-blocking for the web app: it runs in a background
task, uses short transactions and records its status in ``sync_runs``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.core.text import build_search_text
from app.db.base import utcnow
from app.db.models import (
    AppSettings,
    Genre,
    Library,
    MediaGenre,
    MediaItem,
    SyncRun,
)
from app.db.session import AsyncSessionLocal
from app.emby.client import EmbyClient, EmbyError, ITEM_FIELDS
from app.services.settings_service import get_or_create_settings, is_setup_complete

logger = logging.getLogger("guesstheframe.sync")
_sync_lock = asyncio.Lock()
_sync_task: asyncio.Task[None] | None = None
DAILY_SYNC_HOUR = 12
PARIS_TZ = ZoneInfo("Europe/Paris")


def is_sync_running() -> bool:
    return _sync_lock.locked()


def _chunks(values: list[int], size: int = 400) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _clip(value: Any, length: int) -> str | None:
    """Keep Emby metadata inside PostgreSQL VARCHAR limits."""
    if value is None:
        return None
    text = str(value)
    return text[:length]


def _year_from(item: dict[str, Any]) -> int | None:
    year = item.get("ProductionYear")
    if isinstance(year, int):
        return year
    premiere = _parse_datetime(item.get("PremiereDate"))
    return premiere.year if premiere else None


def _pick_source(item: dict[str, Any]) -> dict[str, Any]:
    sources = item.get("MediaSources") or []
    if not isinstance(sources, list):
        return {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("Type") == "Default" and source.get("SupportsDirectPlay"):
            return source
    for source in sources:
        if isinstance(source, dict) and source.get("SupportsDirectStream"):
            return source
    return sources[0] if sources and isinstance(sources[0], dict) else {}


def _video_stream(source: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    streams = source.get("MediaStreams") or item.get("MediaStreams") or []
    if not isinstance(streams, list):
        return {}
    for stream in streams:
        if isinstance(stream, dict) and stream.get("Type") == "Video":
            return stream
    return {}


def _name_list(value: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(value, list):
        return result
    for entry in value:
        if isinstance(entry, dict):
            name = entry.get("Name") or entry.get("name")
            if name:
                result.append(str(name))
        elif entry:
            result.append(str(entry))
    return list(dict.fromkeys(result))


def _collection_list(value: Any) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    if not isinstance(value, list):
        return result
    for entry in value:
        if isinstance(entry, dict):
            name = entry.get("Name") or entry.get("name")
            collection_id = entry.get("Id") or entry.get("id")
            if name or collection_id:
                result.append(
                    {
                        "id": str(collection_id) if collection_id else None,
                        "name": str(name) if name else None,
                    }
                )
        elif entry:
            result.append({"id": None, "name": str(entry)})
    seen: set[str] = set()
    unique: list[dict[str, str | None]] = []
    for item in result:
        key = item["id"] or item["name"] or ""
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _people(item: dict[str, Any]) -> list[dict[str, Any]]:
    people = item.get("People") or []
    result: list[dict[str, Any]] = []
    if not isinstance(people, list):
        return result
    for person in people:
        if not isinstance(person, dict):
            continue
        person_type = person.get("Type")
        if person_type not in {"Director", "Actor"}:
            continue
        name = person.get("Name")
        if not name:
            continue
        result.append(
            {
                "name": str(name),
                "type": str(person_type),
                "role": person.get("Role"),
            }
        )
        if len([p for p in result if p["type"] == "Actor"]) >= 25:
            break
    return result


def _chapters(item: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("Chapters") or source.get("Chapters") or []
    chapters: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return chapters
    for index, chapter in enumerate(raw):
        if not isinstance(chapter, dict):
            continue
        chapters.append(
            {
                "index": chapter.get("ChapterIndex", index),
                "start_ticks": chapter.get("StartPositionTicks"),
                "name": chapter.get("Name"),
                "marker_type": chapter.get("MarkerType"),
                "image_tag": chapter.get("ImageTag"),
            }
        )
    return chapters


def _serialize_source(source: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source.get("Id"),
        "container": source.get("Container"),
        "runtime_ticks": source.get("RunTimeTicks"),
        "bitrate": source.get("Bitrate"),
        "video_range": video.get("VideoRange"),
        "width": video.get("Width"),
        "height": video.get("Height"),
        "codec": video.get("Codec"),
        "supports_direct_play": bool(source.get("SupportsDirectPlay")),
        "supports_direct_stream": bool(source.get("SupportsDirectStream")),
    }


def _series_map_from(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = item.get("Id")
        if item_id:
            mapping[str(item_id)] = {
                "original_title": item.get("OriginalTitle"),
                "sort_name": item.get("SortName"),
            }
    return mapping


async def _fetch_series_map(
    client: EmbyClient, libraries: list[Library]
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for library in libraries:
        if library.collection_type != "tvshows":
            continue
        start = 0
        page_size = 500
        while True:
            payload = await client.get_items(
                parent_id=library.emby_library_id,
                include_item_types="Series",
                start_index=start,
                limit=page_size,
                fields="OriginalTitle,SortName,ProductionYear",
            )
            items = payload.get("Items") or []
            mapping.update(_series_map_from(items))
            total = int(payload.get("TotalRecordCount") or 0)
            start += len(items)
            if not items or len(items) < page_size or start >= total:
                break
    return mapping


def _build_media_payload(
    item: dict[str, Any],
    *,
    library_id: int,
    server_id: str,
    series_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    item_type = item.get("Type")
    if item_type not in {"Movie", "Episode"}:
        return None

    source = _pick_source(item)
    video = _video_stream(source, item)
    media_type = "movie" if item_type == "Movie" else "episode"
    title = item.get("Name")
    if not title:
        return None

    image_tags = item.get("ImageTags") or {}
    backdrops = item.get("BackdropImageTags") or []
    series_id = item.get("SeriesId")
    series_info = series_map.get(str(series_id), {}) if series_id else {}
    episode_title = item.get("Name") if media_type == "episode" else None
    studios = _name_list(item.get("Studios"))
    collections = _collection_list(item.get("Collections"))
    tags = _name_list(item.get("Tags"))
    series_name = item.get("SeriesName")
    series_original_title = series_info.get("original_title") if series_info else None

    return {
        "emby_item_id": _clip(item.get("Id"), 64),
        "emby_server_id": server_id,
        "library_id": library_id,
        "type": media_type,
        "title": _clip(title, 512),
        "original_title": _clip(item.get("OriginalTitle"), 512),
        "sort_title": _clip(item.get("SortName"), 512),
        "year": _year_from(item),
        "overview": item.get("Overview"),
        "runtime_ticks": item.get("RunTimeTicks") or source.get("RunTimeTicks"),
        "official_rating": _clip(item.get("OfficialRating"), 32),
        "community_rating": item.get("CommunityRating"),
        "series_id": _clip(series_id, 64),
        "series_name": _clip(series_name, 512),
        "series_original_title": _clip(series_original_title, 512),
        "season_number": item.get("ParentIndexNumber"),
        "episode_number": item.get("IndexNumber"),
        "episode_title": _clip(episode_title, 512),
        "premiere_date": _parse_datetime(item.get("PremiereDate")),
        "genres": list(dict.fromkeys(item.get("Genres") or [])),
        "people": _people(item),
        "studios": studios,
        "collections": collections,
        "tags": tags,
        "chapters": _chapters(item, source),
        "media_sources": [_serialize_source(source, video)] if source else [],
        "media_source_id": _clip(source.get("Id"), 128),
        "container": _clip(source.get("Container") or item.get("Container"), 32),
        "video_range": _clip(video.get("VideoRange"), 32),
        "width": video.get("Width"),
        "height": video.get("Height"),
        "poster_tag": _clip(
            image_tags.get("Primary") if isinstance(image_tags, dict) else None,
            512,
        ),
        "backdrop_tags": backdrops if isinstance(backdrops, list) else [],
        "search_text": _clip(
            build_search_text(
                str(title),
                item.get("OriginalTitle"),
                item.get("SortName"),
                series_name,
                series_original_title,
                episode_title,
            ),
            1024,
        ),
        "emby_etag": _clip(item.get("Etag") or item.get("DateModified"), 255),
        "date_modified": _parse_datetime(item.get("DateModified")),
        "is_active": True,
        "last_synced_at": utcnow(),
    }


async def _upsert_item(
    db: AsyncSession,
    payload: dict[str, Any],
    *,
    counters: dict[str, int],
) -> None:
    statement = select(MediaItem).where(
        MediaItem.emby_server_id == payload["emby_server_id"],
        MediaItem.emby_item_id == payload["emby_item_id"],
    )
    existing = (await db.execute(statement)).scalar_one_or_none()

    if existing is None:
        media = MediaItem(**payload)
        db.add(media)
        await db.flush()
        counters["added"] += 1
    else:
        unchanged = (
            existing.is_active
            and existing.emby_etag == payload["emby_etag"]
            and existing.date_modified == payload["date_modified"]
        )
        comparable = {
            key: value
            for key, value in payload.items()
            if key not in {"last_synced_at", "is_active"}
        }
        changed = any(
            getattr(existing, key) != value for key, value in comparable.items()
        )
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.is_active = True
        media = existing
        if not unchanged or changed:
            counters["updated"] += 1

    # Refresh the normalised genre links when they changed.
    await db.execute(delete(MediaGenre).where(MediaGenre.media_id == media.id))
    for genre in payload.get("genres") or []:
        if genre:
            db.add(MediaGenre(media_id=media.id, genre=str(genre)))


async def _sync_library(
    db: AsyncSession,
    client: EmbyClient,
    library: Library,
    *,
    server_id: str,
    series_map: dict[str, dict[str, Any]],
    counters: dict[str, int],
) -> set[str]:
    seen: set[str] = set()
    start = 0
    page_size = 200
    scan_ok = True

    while True:
        try:
            payload = await client.get_items(
                parent_id=library.emby_library_id,
                include_item_types="Movie,Episode",
                start_index=start,
                limit=page_size,
                fields=ITEM_FIELDS,
            )
        except EmbyError:
            logger.exception("Emby page fetch failed for library %s", library.name)
            counters["errors"] += 1
            scan_ok = False
            break

        items = payload.get("Items") or []
        total = int(payload.get("TotalRecordCount") or 0)

        for item in items:
            try:
                item_payload = _build_media_payload(
                    item,
                    library_id=library.id,
                    server_id=server_id,
                    series_map=series_map,
                )
                if item_payload is None:
                    continue
                seen.add(item_payload["emby_item_id"])
                counters["items_seen"] += 1
                async with db.begin_nested():
                    await _upsert_item(db, item_payload, counters=counters)
            except Exception:
                counters["errors"] += 1
                logger.exception(
                    "Failed to synchronise item %s", item.get("Id", "unknown")
                )

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            counters["errors"] += 1
            scan_ok = False
            logger.exception(
                "Failed to commit page for library %s", library.name
            )
            break
        start += len(items)
        if not items or len(items) < page_size or (total and start >= total):
            break

    if scan_ok:
        existing = (
            await db.execute(
                select(MediaItem.id, MediaItem.emby_item_id).where(
                    MediaItem.library_id == library.id,
                    MediaItem.is_active.is_(True),
                )
            )
        ).all()
        if not seen and existing:
            logger.warning(
                "Library %s returned no items; skipping deactivation", library.name
            )
            counters["errors"] += 1
        else:
            missing = [row[0] for row in existing if row[1] not in seen]
            for chunk in _chunks(missing):
                await db.execute(
                    update(MediaItem)
                    .where(MediaItem.id.in_(chunk))
                    .values(is_active=False)
                )
                counters["deactivated"] += len(chunk)
        library.item_count = len(seen)
        library.last_synced_at = utcnow()

    return seen


async def _run_sync(
    mode: str, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
) -> int:
    async with session_factory() as db:
        config = await get_or_create_settings(db)
        if not is_setup_complete(config):
            raise AppError(
                "SETUP_REQUIRED",
                "Configurez Emby avant de lancer une synchronisation.",
                status_code=409,
            )

        run = SyncRun(mode=mode, status="running", started_at=utcnow())
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

        counters = {
            "items_seen": 0,
            "added": 0,
            "updated": 0,
            "deactivated": 0,
            "errors": 0,
        }

        try:
            api_key = decrypt_secret(config.emby_api_key_enc)
            if not api_key:
                raise AppError(
                    "EMBY_KEY_MISSING",
                    "La clé API Emby est absente. Reconfigurez le serveur.",
                    status_code=409,
                )

            client = EmbyClient(
                config.emby_url,
                token=api_key,
                verify_tls=config.emby_verify_tls,
                timeout=30.0,
            )
            libraries = (
                await db.execute(
                    select(Library)
                    .where(Library.is_enabled.is_(True))
                    .order_by(Library.name)
                )
            ).scalars().all()

            if not libraries:
                raise AppError(
                    "NO_LIBRARY_ENABLED",
                    "Aucune bibliothèque Emby n'est activée.",
                    status_code=409,
                )

            series_map = await _fetch_series_map(client, list(libraries))
            run.libraries = len(libraries)
            await db.commit()

            for library in libraries:
                logger.info("Synchronising Emby library %s", library.name)
                await _sync_library(
                    db,
                    client,
                    library,
                    server_id=config.emby_server_id or "",
                    series_map=series_map,
                    counters=counters,
                )

            # Persist every genre seen in the catalogue, enabled by default.
            genres = (
                await db.execute(select(MediaGenre.genre).distinct())
            ).scalars().all()
            existing_genres = set(
                (await db.execute(select(Genre.name))).scalars().all()
            )
            for genre in genres:
                if genre and genre not in existing_genres:
                    db.add(Genre(name=genre, is_enabled=True))

            config.last_sync_at = utcnow()
            run.status = "success"
            run.finished_at = utcnow()
            run.items_seen = counters["items_seen"]
            run.added = counters["added"]
            run.updated = counters["updated"]
            run.deactivated = counters["deactivated"]
            run.errors = counters["errors"]
            await db.commit()
            logger.info(
                "Catalogue sync done: %s items, %s added, %s updated, %s deactivated, %s errors",
                counters["items_seen"],
                counters["added"],
                counters["updated"],
                counters["deactivated"],
                counters["errors"],
            )
            return run.id

        except Exception as exc:
            await db.rollback()
            run = await db.get(SyncRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = utcnow()
                run.items_seen = counters["items_seen"]
                run.added = counters["added"]
                run.updated = counters["updated"]
                run.deactivated = counters["deactivated"]
                run.errors = counters["errors"] + 1
                run.error_message = str(exc)[:2000]
                await db.commit()
            logger.exception("Catalogue sync failed")
            if isinstance(exc, AppError):
                raise
            raise AppError(
                "SYNC_FAILED",
                "La synchronisation du catalogue a échoué. Consultez les logs.",
                status_code=502,
                details={"reason": str(exc)},
            ) from exc


async def run_catalog_sync(
    mode: str = "manual",
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> int:
    if _sync_lock.locked():
        raise AppError(
            "SYNC_ALREADY_RUNNING",
            "Une synchronisation est déjà en cours.",
            status_code=409,
        )
    async with _sync_lock:
        return await _run_sync(mode, session_factory)


async def start_background_sync(mode: str = "manual") -> None:
    global _sync_task
    if _sync_task and not _sync_task.done():
        return

    async def _runner() -> None:
        try:
            await run_catalog_sync(mode)
        except Exception:
            logger.exception("Background catalogue sync failed")

    _sync_task = asyncio.create_task(_runner(), name="gtf-catalog-sync")


async def backfill_search_text() -> int:
    """Populate the normalised search column for catalogues synced before it existed."""
    from app.db.models import MediaItem
    from app.db.session import AsyncSessionLocal

    updated = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(
                    MediaItem.id,
                    MediaItem.title,
                    MediaItem.original_title,
                    MediaItem.sort_title,
                    MediaItem.series_name,
                    MediaItem.series_original_title,
                    MediaItem.episode_title,
                ).where(MediaItem.search_text == "")
            )
        ).all()
        for row in rows:
            item = await db.get(MediaItem, row[0])
            if item is None:
                continue
            item.search_text = build_search_text(
                item.title,
                item.original_title,
                item.sort_title,
                item.series_name,
                item.series_original_title,
                item.episode_title,
            )
            updated += 1
            if updated % 200 == 0:
                await db.commit()
        await db.commit()
    if updated:
        logger.info("Backfilled search text for %d media items", updated)
    return updated


async def expire_stale_games() -> int:
    """Abandon games left in progress beyond the configured inactivity delay."""
    from datetime import timedelta

    from sqlalchemy import func, update

    from app.db.models import Game
    from app.db.session import AsyncSessionLocal
    from app.services.settings_service import get_or_create_settings

    async with AsyncSessionLocal() as db:
        config = await get_or_create_settings(db)
        minutes = int(
            (config.game_config or {}).get("game_inactivity_minutes", 60)
        )
        cutoff = utcnow() - timedelta(minutes=max(5, minutes))
        result = await db.execute(
            update(Game)
            .where(
                Game.status == "in_progress",
                func.coalesce(Game.last_activity_at, Game.started_at) < cutoff,
            )
            .values(
                status="abandoned",
                score=0,
                finished_at=utcnow(),
                score_breakdown={"won": False, "reason": "inactivity"},
            )
        )
        await db.commit()
        return int(result.rowcount or 0)


async def _daily_sync_due(
    db: AsyncSession, config: AppSettings, now: datetime
) -> bool:
    """Return True once per day, after 12:00 Europe/Paris."""
    if not config.sync_enabled or not is_setup_complete(config):
        return False
    now_local = now.replace(tzinfo=timezone.utc).astimezone(PARIS_TZ)
    target = now_local.replace(
        hour=DAILY_SYNC_HOUR, minute=0, second=0, microsecond=0
    )
    if now_local < target:
        return False
    latest_attempt = (
        await db.execute(
            select(SyncRun.started_at).order_by(SyncRun.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if latest_attempt is not None:
        latest_local = latest_attempt.replace(tzinfo=timezone.utc).astimezone(
            PARIS_TZ
        )
        if latest_local >= target:
            return False
    return True


async def sync_scheduler() -> None:
    """Periodic sync loop started from the FastAPI lifespan."""
    while True:
        try:
            try:
                await expire_stale_games()
            except Exception:
                logger.exception("Game expiration tick failed")

            try:
                from app.duels.service import finish_expired_duels

                await finish_expired_duels()
            except Exception:
                logger.exception("Duel expiration tick failed")

            async with AsyncSessionLocal() as db:
                config = await get_or_create_settings(db)
                due = await _daily_sync_due(db, config, utcnow())
                if due and not _sync_lock.locked():
                    logger.info("Starting daily catalogue sync (12:00 Europe/Paris)")
                    await start_background_sync("daily")
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(60)


async def stop_background_sync() -> None:
    global _sync_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        try:
            await _sync_task
        except (asyncio.CancelledError, Exception):
            pass
    _sync_task = None
