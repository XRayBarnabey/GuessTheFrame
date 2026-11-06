"""Frame extraction and persistent cache.

The primary source is a real FFmpeg extraction from Emby's static video stream.
Native Emby chapter images and BIF preview thumbnails are used as fallbacks.
Posters are never used as a frame.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import shutil
import struct
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageFilter, ImageStat
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.errors import AppError
from app.db.base import utcnow
from app.db.models import AppSettings, FrameCache, Game, MediaItem
from app.emby.client import EmbyClient

logger = logging.getLogger("guesstheframe.frames")
settings = get_settings()

_ffmpeg_cache: str | None | bool = None
_semaphore: asyncio.Semaphore | None = None
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BIF_MAGIC = b"\x89BIF\r\n\x1a\n"


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.ffmpeg_concurrency))
    return _semaphore


def find_ffmpeg() -> str | None:
    global _ffmpeg_cache
    if _ffmpeg_cache is not None:
        return _ffmpeg_cache or None

    candidate = (settings.ffmpeg_path or "").strip().strip('"')
    if candidate:
        path = Path(candidate)
        if path.is_dir():
            path = path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if path.is_file():
            _ffmpeg_cache = str(path)
            return _ffmpeg_cache

    discovered = shutil.which("ffmpeg")
    _ffmpeg_cache = discovered if discovered else False
    return discovered


def _cache_path(key: str) -> Path:
    return settings.frame_cache_dir / key[:2] / key[2:4] / f"{key}.jpg"


def _cache_key(game_id: str, media_id: int, timestamp_ms: int, width: int) -> str:
    return hashlib.sha256(
        f"{game_id}|{media_id}|{timestamp_ms}|{width}".encode("utf-8")
    ).hexdigest()


def dhash(path: Path) -> str:
    with Image.open(path) as image:
        small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(small.tobytes())
    bits = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            bits = (bits << 1) | (1 if left < right else 0)
    return f"{bits:016x}"


def _hamming(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 64


def validate_image(path: Path) -> tuple[int, int, str]:
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("Fichier image absent ou trop petit.")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            if width < 200 or height < 100:
                raise ValueError("Image trop petite.")
            gray = image.convert("L").resize((160, 90))
            stats = ImageStat.Stat(gray)
            mean = float(stats.mean[0])
            stddev = float(stats.stddev[0])
            if mean < 9 or stddev < 6:
                raise ValueError(f"Image trop sombre ou uniforme (mean={mean:.1f}, std={stddev:.1f}).")
    except Image.UnidentifiedImageError as exc:
        raise ValueError("Fichier image illisible.") from exc
    return width, height, dhash(path)


def _duration_seconds(snapshot: dict[str, Any]) -> float:
    ticks = int(snapshot.get("runtime_ticks") or 0)
    return max(1.0, ticks / 10_000_000)


def _window(snapshot: dict[str, Any]) -> tuple[float, float]:
    duration = _duration_seconds(snapshot)
    if duration < 60:
        return 2.0, max(3.0, duration - 2.0)
    if duration < 300:
        start = max(10.0, duration * 0.08)
        end = max(start + 5.0, duration * 0.9)
    else:
        start = max(90.0, duration * 0.06)
        end = min(duration - 120.0, duration * 0.92)

    intro_end: float | None = None
    credits_start: float | None = None
    for chapter in snapshot.get("chapters") or []:
        marker = str(chapter.get("marker_type") or "")
        ticks = int(chapter.get("start_ticks") or 0)
        seconds = ticks / 10_000_000
        if marker == "IntroEnd":
            intro_end = max(intro_end or 0.0, seconds)
        elif marker == "CreditsStart":
            credits_start = min(credits_start or seconds, seconds)

    if intro_end is not None:
        start = max(start, intro_end + 15.0)
    if credits_start is not None:
        end = min(end, credits_start - 15.0)

    if end <= start + 5.0:
        start = max(10.0, duration * 0.1)
        end = max(start + 5.0, duration * 0.9)
    return start, end


async def _recent_timestamps(db: AsyncSession, media_id: int) -> list[float]:
    rows = (
        await db.execute(
            select(FrameCache.timestamp_ms)
            .where(FrameCache.media_id == media_id)
            .order_by(FrameCache.last_used_at.desc())
            .limit(30)
        )
    ).scalars().all()
    return [value / 1000.0 for value in rows]


async def _recent_hashes(db: AsyncSession, media_id: int) -> list[str]:
    rows = (
        await db.execute(
            select(FrameCache.phash)
            .where(FrameCache.media_id == media_id, FrameCache.phash.is_not(None))
            .order_by(FrameCache.last_used_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return [value for value in rows if value]


def _choose_timestamp(
    snapshot: dict[str, Any], used_timestamps: list[float]
) -> float:
    start, end = _window(snapshot)
    for _ in range(30):
        candidate = random.uniform(start, end)
        if all(abs(candidate - used) >= 30.0 for used in used_timestamps):
            return candidate
    return random.uniform(start, end)


def _ffmpeg_filter(snapshot: dict[str, Any], width: int) -> str:
    video_range = str(snapshot.get("video_range") or "").upper()
    hdr = any(token in video_range for token in ("HDR", "HLG", "DOLBY"))
    scale = f"scale={width}:-2"
    if not hdr:
        return scale
    return (
        "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
        "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"
        f"format=yuv420p,{scale}"
    )


def _run_ffmpeg(command: list[str], timeout: int) -> tuple[int, bytes]:
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    return result.returncode, result.stderr


async def _extract_with_ffmpeg(
    *,
    snapshot: dict[str, Any],
    emby_url: str,
    api_key: str,
    verify_tls: bool,
    timestamp: float,
    width: int,
    output: Path,
) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg introuvable.")

    client = EmbyClient(emby_url, token=api_key, verify_tls=verify_tls)
    item_id = str(snapshot.get("emby_item_id") or "")
    source_id = str(snapshot.get("media_source_id") or "")
    if not item_id or not source_id:
        raise RuntimeError("Source média Emby incomplète.")

    stream_url = client.stream_url(
        item_id, source_id, container=snapshot.get("container")
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-headers",
        f"X-Emby-Token: {api_key}\r\n",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        stream_url,
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-vf",
        _ffmpeg_filter(snapshot, width),
        "-q:v",
        "3",
        "-y",
        str(output),
    ]

    async with _sem():
        try:
            code, stderr = await asyncio.to_thread(
                _run_ffmpeg, command, settings.ffmpeg_timeout_seconds
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Extraction FFmpeg expirée.") from exc
        except OSError as exc:
            raise RuntimeError(f"Impossible de lancer FFmpeg : {exc}") from exc

    if code != 0 or not output.is_file():
        tail = stderr.decode("utf-8", errors="replace")[-600:]
        raise RuntimeError(f"FFmpeg a échoué (code {code}) : {tail}")


async def _fetch_bytes(url: str, token: str, verify_tls: bool) -> tuple[bytes, str]:
    async with httpx.AsyncClient(
        verify=verify_tls, timeout=30.0, follow_redirects=True
    ) as client:
        response = await client.get(url, headers={"X-Emby-Token": token})
    if response.status_code == 404:
        raise FileNotFoundError(url)
    if response.status_code >= 400:
        raise RuntimeError(f"Emby a répondu {response.status_code} pour {url}")
    return response.content, response.headers.get("content-type", "image/jpeg")


def parse_bif(data: bytes) -> list[bytes]:
    if len(data) < 20 or not data.startswith(BIF_MAGIC):
        return []
    _version, count, _interval = struct.unpack_from("<III", data, 8)
    if count <= 0 or count > 100_000:
        return []
    entries: list[tuple[int, int, int]] = []
    offset = 20
    for _ in range(count):
        if offset + 16 > len(data):
            break
        _timestamp, image_offset, length = struct.unpack_from("<QII", data, offset)
        entries.append((_timestamp, image_offset, length))
        offset += 16

    images: list[bytes] = []
    for _timestamp, image_offset, length in entries:
        end = image_offset + length
        if image_offset <= 0 or length <= 0 or end > len(data):
            continue
        images.append(data[image_offset:end])
    return images


async def _fallback_native(
    db: AsyncSession,
    *,
    game: Game,
    snapshot: dict[str, Any],
    media: MediaItem,
    config: AppSettings,
    api_key: str,
    width: int,
    recent_hashes: list[str],
) -> Path | None:
    client = EmbyClient(
        config.emby_url, token=api_key, verify_tls=config.emby_verify_tls
    )
    item_id = str(snapshot.get("emby_item_id") or media.emby_item_id)

    chapters = list(snapshot.get("chapters") or [])
    candidates = [
        chapter
        for chapter in chapters
        if chapter.get("image_tag") is not None and chapter.get("index") is not None
    ]
    random.shuffle(candidates)

    for chapter in candidates:
        index = int(chapter["index"])
        url = client.image_url(
            item_id, "Chapter", index=index, max_width=width
        )
        output = settings.frame_cache_dir / "tmp" / f"{uuid.uuid4().hex}.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            content, _content_type = await _fetch_bytes(
                url, api_key, config.emby_verify_tls
            )
            output.write_bytes(content)
            image_width, image_height, phash = validate_image(output)
            if any(_hamming(phash, previous) < 8 for previous in recent_hashes):
                output.unlink(missing_ok=True)
                continue
            timestamp_ms = int(int(chapter.get("start_ticks") or 0) / 10_000)
            key = _cache_key(game.id, media.id, timestamp_ms, width)
            target = _cache_path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            output.replace(target)
            await _store_cache(
                db,
                game=game,
                media=media,
                key=key,
                timestamp_ms=timestamp_ms,
                source="emby_chapter",
                width=image_width,
                height=image_height,
                size=target.stat().st_size,
                phash=phash,
            )
            return target
        except (FileNotFoundError, RuntimeError, ValueError):
            output.unlink(missing_ok=True)

    # BIF preview thumbnails (Roku metadata), if enabled on the Emby library.
    try:
        bif_url = f"{client.api_root}/Videos/{item_id}/index.bif"
        content, _content_type = await _fetch_bytes(
            bif_url, api_key, config.emby_verify_tls
        )
        images = parse_bif(content)
        random.shuffle(images)
        for image_bytes in images[:40]:
            output = settings.frame_cache_dir / "tmp" / f"{uuid.uuid4().hex}.jpg"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(image_bytes)
            try:
                image_width, image_height, phash = validate_image(output)
            except ValueError:
                output.unlink(missing_ok=True)
                continue
            if any(_hamming(phash, previous) < 8 for previous in recent_hashes):
                output.unlink(missing_ok=True)
                continue
            key = _cache_key(game.id, media.id, random.randint(0, 10_000_000), width)
            target = _cache_path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            output.replace(target)
            await _store_cache(
                db,
                game=game,
                media=media,
                key=key,
                timestamp_ms=0,
                source="emby_bif",
                width=image_width,
                height=image_height,
                size=target.stat().st_size,
                phash=phash,
            )
            return target
    except (FileNotFoundError, RuntimeError):
        pass

    return None


async def _store_cache(
    db: AsyncSession,
    *,
    game: Game,
    media: MediaItem,
    key: str,
    timestamp_ms: int,
    source: str,
    width: int,
    height: int,
    size: int,
    phash: str,
) -> None:
    existing = await db.get(FrameCache, key)
    if existing is None:
        db.add(
            FrameCache(
                cache_key=key,
                media_id=media.id,
                timestamp_ms=timestamp_ms,
                source=source,
                width=width,
                height=height,
                bytes=size,
                phash=phash,
                created_at=utcnow(),
                last_used_at=utcnow(),
            )
        )
    else:
        existing.last_used_at = utcnow()
    keys = list(game.frame_keys or [])
    if key not in keys:
        keys.append(key)
    game.frame_keys = keys
    if not game.frame_cache_key:
        game.frame_cache_key = key
    await db.commit()


_GAME_LOCKS: dict[str, asyncio.Lock] = {}


def _game_lock(game_id: str) -> asyncio.Lock:
    lock = _GAME_LOCKS.get(game_id)
    if lock is None:
        lock = asyncio.Lock()
        _GAME_LOCKS[game_id] = lock
    return lock


FRAME_COUNTS = {
    "classic": 1,
    "frames3": 3,
    "frames5": 5,
    "dezoom": 1,
    "daily": 1,
}


async def _generate_one(
    db: AsyncSession,
    *,
    game: Game,
    config: AppSettings,
    media: MediaItem,
    snapshot: dict[str, Any],
    api_key: str,
    width: int,
) -> Path:
    used_timestamps = await _recent_timestamps(db, media.id)
    recent_hashes = await _recent_hashes(db, media.id)
    ffmpeg_available = bool(find_ffmpeg())
    errors: list[str] = []

    if ffmpeg_available:
        for _ in range(4):
            timestamp = _choose_timestamp(snapshot, used_timestamps)
            output = settings.frame_cache_dir / "tmp" / f"{uuid.uuid4().hex}.jpg"
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                await _extract_with_ffmpeg(
                    snapshot=snapshot,
                    emby_url=config.emby_url,
                    api_key=api_key,
                    verify_tls=config.emby_verify_tls,
                    timestamp=timestamp,
                    width=width,
                    output=output,
                )
                image_width, image_height, phash = validate_image(output)
                if any(_hamming(phash, previous) < 8 for previous in recent_hashes):
                    errors.append("Frame trop similaire à une précédente.")
                    output.unlink(missing_ok=True)
                    used_timestamps.append(timestamp)
                    continue

                timestamp_ms = int(timestamp * 1000)
                key = _cache_key(game.id, media.id, timestamp_ms, width)
                target = _cache_path(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                output.replace(target)
                await _store_cache(
                    db,
                    game=game,
                    media=media,
                    key=key,
                    timestamp_ms=timestamp_ms,
                    source="ffmpeg",
                    width=image_width,
                    height=image_height,
                    size=target.stat().st_size,
                    phash=phash,
                )
                logger.info(
                    "Frame extracted for game %s at %.1fs (%dx%d)",
                    game.id,
                    timestamp,
                    image_width,
                    image_height,
                )
                return target
            except (RuntimeError, ValueError, OSError) as exc:
                errors.append(str(exc))
                output.unlink(missing_ok=True)
                logger.warning("Frame extraction attempt failed: %s", exc)
    else:
        errors.append("FFmpeg introuvable.")

    native = await _fallback_native(
        db,
        game=game,
        snapshot=snapshot,
        media=media,
        config=config,
        api_key=api_key,
        width=width,
        recent_hashes=recent_hashes,
    )
    if native:
        logger.info("Native Emby frame used for game %s", game.id)
        return native

    raise AppError(
        "FRAME_UNAVAILABLE",
        "Impossible d'extraire une véritable image pour ce média. Réessayez ou lancez une nouvelle partie.",
        status_code=503,
        details={"attempts": errors[-3:]},
    )


async def ensure_frame(
    db: AsyncSession, game: Game, config: AppSettings, index: int = 0
) -> Path:
    mode = game.mode or "classic"
    count = FRAME_COUNTS.get(mode, 1)
    if index < 0 or index >= count:
        raise AppError("FRAME_INDEX_INVALID", "Index d'image invalide.", status_code=404)

    lock = _game_lock(game.id)
    async with lock:
        keys = list(game.frame_keys or [])
        if not keys and game.frame_cache_key:
            keys = [game.frame_cache_key]
            game.frame_keys = keys
            await db.commit()

        if index < len(keys):
            existing_path = _cache_path(keys[index])
            if existing_path.is_file():
                cache = await db.get(FrameCache, keys[index])
                if cache:
                    cache.last_used_at = utcnow()
                    await db.commit()
                return existing_path
            keys = keys[:index]
            game.frame_keys = keys
            await db.commit()

        media = await db.get(MediaItem, game.media_id)
        if media is None:
            raise AppError(
                "MEDIA_DELETED",
                "Ce média a été supprimé d'Emby.",
                status_code=410,
            )

        snapshot = dict(game.media_snapshot or {})
        if not snapshot:
            raise AppError(
                "FRAME_UNAVAILABLE",
                "Métadonnées du média indisponibles.",
                status_code=503,
            )

        api_key = decrypt_secret(config.emby_api_key_enc)
        if not api_key:
            raise AppError(
                "EMBY_NOT_CONFIGURED",
                "La clé API Emby n'est pas configurée.",
                status_code=409,
            )

        game_config = config.game_config or {}
        width = max(320, min(1920, int(game_config.get("frame_width", 1280))))

        for _slot in range(len(keys), index + 1):
            await _generate_one(
                db,
                game=game,
                config=config,
                media=media,
                snapshot=snapshot,
                api_key=api_key,
                width=width,
            )
            keys = list(game.frame_keys or [])
            if len(keys) <= _slot:
                raise AppError(
                    "FRAME_UNAVAILABLE",
                    "Impossible de générer l'image demandée.",
                    status_code=503,
                )

        return _cache_path(keys[index])


def dezoom_factor(attempts_count: int) -> float:
    return round(max(1.0, 2.8 - 0.35 * max(0, attempts_count)), 2)


async def apply_dezoom(frame_path: Path, frame_key: str, attempts_count: int) -> Path:
    factor = dezoom_factor(attempts_count)
    if factor <= 1.01:
        return frame_path

    target = settings.frame_cache_dir / "zoom" / f"{frame_key}-{factor:.2f}.jpg"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    def _crop() -> None:
        with Image.open(frame_path) as image:
            width, height = image.size
            crop_width = max(1, int(width / factor))
            crop_height = max(1, int(height / factor))
            best_crop = None
            best_score = -1.0
            # Pick the most detailed/bright area rather than a black corner.
            for fy in (0.12, 0.5, 0.88):
                for fx in (0.12, 0.5, 0.88):
                    left = int((width - crop_width) * fx)
                    top = int((height - crop_height) * fy)
                    candidate = image.crop(
                        (left, top, left + crop_width, top + crop_height)
                    )
                    probe = candidate.convert("L").resize((64, 36))
                    stats = ImageStat.Stat(probe)
                    score = float(stats.mean[0]) + 1.4 * float(stats.stddev[0])
                    if score > best_score:
                        best_score = score
                        best_crop = candidate
            if best_crop is None:
                return
            cropped = best_crop.resize((width, height), Image.Resampling.LANCZOS)
            cropped.convert("RGB").save(target, format="JPEG", quality=88)

    try:
        await asyncio.to_thread(_crop)
        return target
    except Exception:
        logger.exception("Dezoom crop failed; serving the full frame")
        return frame_path


async def apply_blur(frame_path: Path, frame_key: str, radius: int = 18) -> Path:
    target = settings.frame_cache_dir / "blur" / f"{frame_key}-{radius}.jpg"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    def _blur() -> None:
        with Image.open(frame_path) as image:
            blurred = image.convert("RGB").filter(
                ImageFilter.GaussianBlur(radius=radius)
            )
            blurred.save(target, format="JPEG", quality=85)

    try:
        await asyncio.to_thread(_blur)
        return target
    except Exception:
        logger.exception("Blur failed; serving the original frame")
        return frame_path
