from __future__ import annotations

from io import BytesIO

import httpx
import respx
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.models import DailyChallenge, Game, MediaItem
from app.emby.sync import run_catalog_sync

EMBY = "http://emby.test/emby"
MOVIE_ID = "movie1"
LIBRARY_ID = "lib-movies"


def _movie_payload() -> dict:
    return {
        "Id": MOVIE_ID,
        "Name": "Inception",
        "OriginalTitle": "Inception",
        "SortName": "Inception",
        "Type": "Movie",
        "Etag": "etag-movie-1",
        "DateModified": "2024-01-01T00:00:00.0000000Z",
        "PremiereDate": "2010-07-16T00:00:00.0000000Z",
        "ProductionYear": 2010,
        "Overview": "Un voleur d'idées.",
        "RunTimeTicks": 88_800_000_000,
        "Genres": ["Science-Fiction", "Thriller"],
        "OfficialRating": "PG-13",
        "CommunityRating": 8.8,
        "People": [
            {"Name": "Christopher Nolan", "Type": "Director"},
            {"Name": "Leonardo DiCaprio", "Type": "Actor"},
            {"Name": "Joseph Gordon-Levitt", "Type": "Actor"},
        ],
        "MediaSources": [
            {
                "Id": "ms1",
                "Type": "Default",
                "Container": "mkv",
                "RunTimeTicks": 88_800_000_000,
                "SupportsDirectPlay": True,
                "SupportsDirectStream": True,
                "MediaStreams": [
                    {
                        "Type": "Video",
                        "Codec": "h264",
                        "VideoRange": "SDR",
                        "Width": 1920,
                        "Height": 1080,
                    }
                ],
            }
        ],
        "ImageTags": {"Primary": "tag-primary"},
        "BackdropImageTags": ["tag-backdrop"],
        "Chapters": [],
    }


def _auth_payload() -> dict:
    return {
        "User": {
            "Id": "user1",
            "Name": "admin",
            "ServerId": "server1",
            "Policy": {"IsDisabled": False, "IsAdministrator": True},
        },
        "AccessToken": "emby-user-token",
        "ServerId": "server1",
    }


def _register_emby(mock: respx.MockRouter, *, access_ok: bool = True) -> None:
    mock.get(f"{EMBY}/System/Info/Public").mock(
        return_value=httpx.Response(
            200,
            json={
                "Id": "server1",
                "ServerName": "Test Emby",
                "Version": "4.10.1.0",
            },
        )
    )
    mock.get(f"{EMBY}/System/Info").mock(
        return_value=httpx.Response(
            200, json={"Id": "server1", "OperatingSystem": "Windows"}
        )
    )
    mock.get(f"{EMBY}/Library/MediaFolders").mock(
        return_value=httpx.Response(
            200,
            json={
                "Items": [
                    {
                        "Id": LIBRARY_ID,
                        "Name": "Films",
                        "CollectionType": "movies",
                        "RecursiveItemCount": 1,
                    }
                ],
                "TotalRecordCount": 1,
            },
        )
    )
    mock.post(f"{EMBY}/Users/AuthenticateByName").mock(
        return_value=httpx.Response(200, json=_auth_payload())
    )
    mock.post(f"{EMBY}/Sessions/Logout").mock(
        return_value=httpx.Response(204)
    )
    mock.get(f"{EMBY}/Users/user1/Items").mock(
        return_value=httpx.Response(
            200,
            json={
                "Items": [{"Id": MOVIE_ID, "Name": "Inception", "Type": "Movie"}]
                if access_ok
                else [],
                "TotalRecordCount": 1 if access_ok else 0,
            },
        )
    )


async def _setup_and_login(
    client: AsyncClient, monkeypatch
) -> tuple[str, dict]:
    config = get_settings()
    monkeypatch.setattr(config, "setup_token", "test-setup-token")

    setup = await client.post(
        "/api/setup/emby",
        json={
            "url": "http://emby.test",
            "api_key": "api-key-test",
            "verify_tls": True,
            "setup_token": "test-setup-token",
        },
    )
    assert setup.status_code == 200, setup.text

    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret"},
    )
    assert login.status_code == 200, login.text
    payload = login.json()
    return payload["csrf_token"], payload["user"]


async def test_setup_rejects_invalid_token(client: AsyncClient, monkeypatch) -> None:
    config = get_settings()
    monkeypatch.setattr(config, "setup_token", "expected-token")

    response = await client.post(
        "/api/setup/emby",
        json={
            "url": "http://emby.test",
            "api_key": "api-key-test",
            "verify_tls": True,
            "setup_token": "wrong-token",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SETUP_TOKEN_INVALID"


async def test_setup_login_and_session_cookie(
    client: AsyncClient, monkeypatch
) -> None:
    config = get_settings()
    monkeypatch.setattr(config, "setup_token", "test-setup-token")

    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)

        setup = await client.post(
            "/api/setup/emby",
            json={
                "url": "http://emby.test",
                "api_key": "api-key-test",
                "verify_tls": True,
                "setup_token": "test-setup-token",
            },
        )
        assert setup.status_code == 200, setup.text
        assert setup.json()["server_name"] == "Test Emby"

        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["user"]["is_admin"] is True
        assert "emby-user-token" not in login.text
        cookie = login.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["username"] == "admin"

        csrf = body["csrf_token"]
        logout = await client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": csrf}
        )
        assert logout.status_code == 200
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_sync_catalogue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        await _setup_and_login(client, monkeypatch)

        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )

        run_id = await run_catalog_sync("test", session_factory)
        assert run_id > 0

        async with session_factory() as db:
            count = (
                await db.execute(select(func.count()).select_from(MediaItem))
            ).scalar_one()
            assert count == 1
            media = (
                await db.execute(select(MediaItem).where(MediaItem.emby_item_id == MOVIE_ID))
            ).scalar_one()
            assert media.title == "Inception"
            assert media.type == "movie"
            assert media.media_source_id == "ms1"
            assert media.runtime_ticks == 88_800_000_000
            assert "Science-Fiction" in media.genres


async def test_full_game_flow(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)

        headers = {"X-CSRF-Token": csrf}
        created = await client.post(
            "/api/games",
            json={
                "media_types": ["movie", "episode"],
                "genres": [],
                "difficulty": "normal",
                "exclude_solved": False,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        game = created.json()
        game_id = game["id"]
        assert game["status"] == "in_progress"
        assert game["ranking_category"] == "general"
        assert "Inception" not in created.text
        assert MOVIE_ID not in created.text

        missing_csrf = await client.post(
            f"/api/games/{game_id}/attempts", json={"guess": "Inception"}
        )
        assert missing_csrf.status_code == 403

        hint = await client.post(f"/api/games/{game_id}/hints", headers=headers)
        assert hint.status_code == 200, hint.text
        hint_body = hint.json()
        assert hint_body["hint"]["key"] == "release_date"
        assert hint_body["hint"]["value"] == "2010"

        wrong = await client.post(
            f"/api/games/{game_id}/attempts",
            json={"guess": "Interstellar"},
            headers=headers,
        )
        assert wrong.status_code == 200
        assert wrong.json()["correct"] is False
        assert "Inception" not in wrong.text

        correct = await client.post(
            f"/api/games/{game_id}/attempts",
            json={"guess": "Inception"},
            headers=headers,
        )
        assert correct.status_code == 200, correct.text
        correct_body = correct.json()
        assert correct_body["correct"] is True
        assert correct_body["result"]["media"]["title"] == "Inception"
        assert correct_body["result"]["score"] == 85
        assert correct_body["result"]["emby_server_name"] == "Test Emby"
        assert correct_body["result"]["media"]["emby_url"].startswith(
            "http://emby.test/web/index.html"
        )

        replay = await client.post(
            f"/api/games/{game_id}/attempts",
            json={"guess": "Inception"},
            headers=headers,
        )
        assert replay.status_code == 409

        result = await client.get(f"/api/games/{game_id}/result")
        assert result.status_code == 200
        assert result.json()["won"] is True

        leaderboard = await client.get("/api/leaderboard")
        assert leaderboard.status_code == 200
        assert leaderboard.json()["category"] == "general"
        assert leaderboard.json()["entries"][0]["username"] == "admin"
        assert leaderboard.json()["entries"][0]["wins"] == 1

        profile = await client.get("/api/users/me/stats")
        assert profile.status_code == 200
        assert profile.json()["games"] == 1
        assert profile.json()["wins"] == 1
        assert profile.json()["score"] == 85

        history = await client.get("/api/users/me/games")
        assert history.status_code == 200
        assert history.json()["items"][0]["title"] == "Inception"

        # Poster proxy uses the Emby API key, never exposes it to the browser.
        buffer = BytesIO()
        Image.new("RGB", (40, 60), (120, 90, 30)).save(buffer, format="JPEG")
        mock.get(f"{EMBY}/Items/{MOVIE_ID}/Images/Primary").mock(
            return_value=httpx.Response(
                200, content=buffer.getvalue(), headers={"content-type": "image/jpeg"}
            )
        )
        poster = await client.get(history.json()["items"][0]["poster_url"])
        assert poster.status_code == 200
        assert poster.headers["content-type"].startswith("image/jpeg")

        async with session_factory() as db:
            stored = (await db.execute(select(Game))).scalar_one()
            assert stored.status == "won"
            assert stored.score == 85
            assert stored.finished_at is not None


async def test_abandon_game_scores_zero(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)

        headers = {"X-CSRF-Token": csrf}
        created = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        assert created.status_code == 201
        game_id = created.json()["id"]

        abandoned = await client.post(
            f"/api/games/{game_id}/abandon", headers=headers
        )
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "abandoned"
        assert abandoned.json()["score"] == 0
        assert abandoned.json()["media"]["title"] == "Inception"


async def test_frame_access_and_headers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
    tmp_path,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)

        created = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers={"X-CSRF-Token": csrf},
        )
        game_id = created.json()["id"]

        frame_path = tmp_path / "frame.jpg"
        Image.new("RGB", (320, 180), (90, 80, 70)).save(frame_path)

        async def fake_ensure_frame(db, game, config, index=0):  # type: ignore[no-untyped-def]
            game.frame_cache_key = "test"
            game.frame_keys = ["test"]
            await db.commit()
            return frame_path

        monkeypatch.setattr("app.games.router.ensure_frame", fake_ensure_frame)

        response = await client.get(f"/api/games/{game_id}/frame")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"].startswith("private")
        assert "emby" not in response.headers


async def test_admin_settings_users_and_emby_update(
    client: AsyncClient, monkeypatch
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        headers = {"X-CSRF-Token": csrf}

        settings_response = await client.get("/api/admin/settings")
        assert settings_response.status_code == 200
        current = settings_response.json()

        updated = await client.put(
            "/api/admin/settings",
            headers=headers,
            json={
                "sync_enabled": True,
                "sync_interval_minutes": 120,
                "game_config": {**current["game_config"], "base_points": 120},
                "hint_config": current["hint_config"],
                "difficulty_config": current["difficulty_config"],
            },
        )
        assert updated.status_code == 200, updated.text

        reread = await client.get("/api/admin/settings")
        assert reread.json()["game_config"]["base_points"] == 120
        assert reread.json()["sync_interval_minutes"] == 120

        users = await client.get("/api/admin/users")
        assert users.status_code == 200
        assert users.json()["users"][0]["username"] == "admin"
        assert users.json()["users"][0]["is_admin"] is True

        emby = await client.put(
            "/api/admin/emby",
            headers=headers,
            json={
                "url": "http://emby.test",
                "api_key": "api-key-test",
                "verify_tls": True,
            },
        )
        assert emby.status_code == 200, emby.text
        assert emby.json()["server_name"] == "Test Emby"

        cache = await client.get("/api/admin/cache")
        assert cache.status_code == 200
        assert "files" in cache.json()


async def test_modes_search_and_selectable_hints(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}

        created = await client.post(
            "/api/games",
            json={
                "media_types": ["movie"],
                "difficulty": "normal",
                "mode": "frames3",
                "exclude_solved": False,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        game = created.json()
        assert game["mode"] == "frames3"
        assert game["frame_count"] == 3
        assert len(game["frame_urls"]) == 3

        search = await client.get("/api/catalogue/titles?q=incep")
        assert search.status_code == 200
        titles = search.json()["items"]
        assert titles[0]["title"] == "Inception"
        assert "movie1" not in search.text
        assert "id" not in titles[0]

        hint = await client.post(
            f"/api/games/{game['id']}/hints",
            json={"hint_key": "director"},
            headers=headers,
        )
        assert hint.status_code == 200, hint.text
        assert hint.json()["hint"]["value"] == "Christopher Nolan"

        duplicate = await client.post(
            f"/api/games/{game['id']}/hints",
            json={"hint_key": "director"},
            headers=headers,
        )
        assert duplicate.status_code == 409


async def test_valid_hint_without_metadata_is_not_charged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        created = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers={"X-CSRF-Token": csrf},
        )
        game_id = created.json()["id"]
        before = created.json()["hints_used"]

        response = await client.post(
            f"/api/games/{game_id}/hints",
            json={"hint_key": "franchise"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "HINT_UNAVAILABLE"
        after = (await client.get(f"/api/games/{game_id}")).json()
        assert after["hints_used"] == before


async def test_daily_mode_is_stable_and_unique(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}

        first = await client.post("/api/games", json={"mode": "daily"}, headers=headers)
        second = await client.post("/api/games", json={"mode": "daily"}, headers=headers)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["mode"] == "daily"
        assert first.json()["daily_date"]

        async with session_factory() as db:
            count = (
                await db.execute(select(func.count()).select_from(DailyChallenge))
            ).scalar_one()
            assert count == 1


async def test_leaderboard_opt_out(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}
        created = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        game_id = created.json()["id"]
        await client.post(
            f"/api/games/{game_id}/attempts",
            json={"guess": "Inception"},
            headers=headers,
        )
        assert (await client.get("/api/leaderboard?category=movies")).json()["entries"]

        hidden = await client.put(
            "/api/users/me/preferences",
            json={"show_in_leaderboard": False},
            headers=headers,
        )
        assert hidden.status_code == 200
        assert hidden.json()["show_in_leaderboard"] is False
        assert (
            await client.get("/api/leaderboard?category=movies")
        ).json()["entries"] == []

        # A movie-only game is not part of the general (movies + series) ranking.
        assert (await client.get("/api/leaderboard?category=general")).json()["entries"] == []

        stats = await client.get("/api/users/me/stats")
        assert stats.json()["wins"] == 1
        assert stats.json()["show_in_leaderboard"] is False


async def test_active_game_blocks_new_game_and_expires(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}
        first = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        assert first.status_code == 201
        game_id = first.json()["id"]

        blocked = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "ACTIVE_GAME_EXISTS"
        assert blocked.json()["error"]["details"]["game_id"] == game_id

        # Simulate an hour without activity.
        from datetime import timedelta

        from app.db.base import utcnow
        from app.db.models import AppSettings, Game
        from app.games.service import expire_user_inactive_games

        async with session_factory() as db:
            game = await db.get(Game, game_id)
            assert game is not None
            game.last_activity_at = utcnow() - timedelta(hours=2)
            await db.commit()
            config = (
                await db.execute(select(AppSettings).where(AppSettings.id == 1))
            ).scalar_one()
            expired = await expire_user_inactive_games(
                db, user_id=game.user_id, config=config
            )
            assert expired == 1
            await db.refresh(game)
            assert game.status == "abandoned"
            assert game.score == 0

        retry = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        assert retry.status_code == 201
        assert retry.json()["id"] != game_id


async def test_admin_can_reset_user_history(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, user = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200,
                json={"Items": [_movie_payload()], "TotalRecordCount": 1},
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}
        created = await client.post(
            "/api/games",
            json={"media_types": ["movie"], "difficulty": "normal", "exclude_solved": False},
            headers=headers,
        )
        game_id = created.json()["id"]
        await client.post(
            f"/api/games/{game_id}/attempts",
            json={"guess": "Inception"},
            headers=headers,
        )
        assert (await client.get("/api/users/me/stats")).json()["games"] == 1

        reset = await client.delete(
            f"/api/admin/users/{user['id']}/history", headers=headers
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["deleted_games"] == 1
        assert (await client.get("/api/users/me/stats")).json()["games"] == 0
        assert (await client.get("/api/leaderboard?category=movies")).json()["entries"] == []


async def test_duel_1v1_flow(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    from datetime import timedelta

    from httpx import ASGITransport, AsyncClient as HttpxClient

    from app.core.crypto import hash_token
    from app.db.base import utcnow
    from app.db.models import DuelFrame, DuelMatch, User, UserSession
    from app.main import app

    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, admin_user = await _setup_and_login(client, monkeypatch)
        items = []
        for index in range(10):
            item = _movie_payload()
            item["Id"] = f"movie-duel-{index}"
            item["Name"] = f"Film Duel {index}"
            item["OriginalTitle"] = f"Film Duel {index}"
            item["SortName"] = f"Film Duel {index}"
            item["MediaSources"][0]["Id"] = f"ms-duel-{index}"
            items.append(item)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200, json={"Items": items, "TotalRecordCount": len(items)}
            )
        )
        await run_catalog_sync("test", session_factory)

        async with session_factory() as db:
            second = User(
                emby_user_id="duel-user-2",
                emby_server_id="server1",
                username="Challenger",
                username_norm="challenger",
                is_admin=False,
            )
            db.add(second)
            await db.flush()
            db.add(
                UserSession(
                    user_id=second.id,
                    token_hash=hash_token("duel-session-2"),
                    csrf_token="duel-csrf-2",
                    emby_token_enc=None,
                    created_at=utcnow(),
                    last_seen_at=utcnow(),
                    emby_checked_at=utcnow(),
                    expires_at=utcnow() + timedelta(days=1),
                )
            )
            await db.commit()

        async with HttpxClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"gtf_session": "duel-session-2"},
        ) as client2:
            admin_headers = {"X-CSRF-Token": csrf}
            second_headers = {"X-CSRF-Token": "duel-csrf-2"}

            created = await client.post(
                "/api/duels",
                json={"categories": ["movie"], "genres": []},
                headers=admin_headers,
            )
            assert created.status_code == 201, created.text
            duel = created.json()
            match_id = duel["id"]
            code = duel["code"]
            assert len(duel["frames"]) == 0
            assert len(code) == 4 and code.isdigit()

            joined = await client2.post(
                "/api/duels/join", json={"code": code}, headers=second_headers
            )
            assert joined.status_code == 200, joined.text
            assert joined.json()["phase"] == "dice"
            assert len(joined.json()["frames"]) == 5
            second_user_id = joined.json()["you"]["user_id"]

            state = joined.json()
            for _ in range(12):
                first_roll = await client.post(
                    f"/api/duels/{match_id}/roll", headers=admin_headers
                )
                second_roll = await client2.post(
                    f"/api/duels/{match_id}/roll", headers=second_headers
                )
                assert first_roll.status_code == 200, first_roll.text
                assert second_roll.status_code == 200, second_roll.text
                state = second_roll.json()
                if state["phase"] == "settings":
                    break
            assert state["phase"] == "settings"

            setter_client = (
                client
                if state["settings_setter_id"] == admin_user["id"]
                else client2
            )
            setter_headers = (
                admin_headers
                if state["settings_setter_id"] == admin_user["id"]
                else second_headers
            )
            configured = await setter_client.post(
                f"/api/duels/{match_id}/settings",
                json={"exchange_count": 1, "duration_seconds": 600},
                headers=setter_headers,
            )
            assert configured.status_code == 200, configured.text
            assert configured.json()["phase"] == "exchange"

            admin_state = (
                await client.get(f"/api/duels/{match_id}")
            ).json()
            second_state = (
                await client2.get(f"/api/duels/{match_id}")
            ).json()
            admin_frame = admin_state["frames"][0]["id"]
            second_frame = second_state["frames"][0]["id"]
            exchanged_admin = await client.post(
                f"/api/duels/{match_id}/exchange",
                json={"frame_ids": [admin_frame]},
                headers=admin_headers,
            )
            exchanged_second = await client2.post(
                f"/api/duels/{match_id}/exchange",
                json={"frame_ids": [second_frame]},
                headers=second_headers,
            )
            assert exchanged_admin.status_code == 200, exchanged_admin.text
            assert exchanged_second.status_code == 200, exchanged_second.text
            assert exchanged_second.json()["phase"] == "playing"

            admin_playing = (
                await client.get(f"/api/duels/{match_id}")
            ).json()
            hint_frame = admin_playing["frames"][0]
            hint_key = next(
                option["key"]
                for option in hint_frame["hint_options"]
                if not option["used"]
            )
            hint_response = await client.post(
                f"/api/duels/{match_id}/frames/{hint_frame['id']}/hints",
                json={"hint_key": hint_key},
                headers=admin_headers,
            )
            assert hint_response.status_code == 200, hint_response.text
            assert hint_response.json()["hint"]["value"]

            # Solve all frames for both players using the server-side snapshots.
            async with session_factory() as db:
                frames = (
                    await db.execute(
                        select(DuelFrame).where(DuelFrame.match_id == match_id)
                    )
                ).scalars().all()
                titles_by_user: dict[int, list[str]] = {}
                for frame in frames:
                    titles_by_user.setdefault(frame.holder_id, []).append(
                        frame.media_snapshot["title"]
                    )

            for user_id in titles_by_user:
                target_client = client if user_id == admin_user["id"] else client2
                target_headers = (
                    admin_headers if user_id == admin_user["id"] else second_headers
                )
                state = (
                    await target_client.get(f"/api/duels/{match_id}")
                ).json()
                for frame in state["frames"]:
                    # The media is not exposed until solved; use the DB mapping.
                    title = next(
                        frame_row.media_snapshot["title"]
                        for frame_row in frames
                        if frame_row.id == frame["id"]
                    )
                    guess = await target_client.post(
                        f"/api/duels/{match_id}/frames/{frame['id']}/guess",
                        json={"guess": title},
                        headers=target_headers,
                    )
                    assert guess.status_code == 200, guess.text
                    assert guess.json()["correct"] is True

            final_state = (await client.get(f"/api/duels/{match_id}")).json()
            assert final_state["phase"] == "finished"
            assert final_state["result"]["players"]
            assert len(final_state["result"]["frames"]) == 10
            result_frames = final_state["result"]["frames"]
            assert all(frame["original_owner_username"] for frame in result_frames)
            assert all(frame["holder_username"] for frame in result_frames)
            assert any(frame["exchanged"] for frame in result_frames)
            assert any(frame["hints"] for frame in result_frames)

            duel_board = await client.get("/api/leaderboard/duel")
            assert duel_board.status_code == 200
            assert len(duel_board.json()["entries"]) == 2

            async with session_factory() as db:
                stored = await db.get(DuelMatch, match_id)
                assert stored is not None
                assert stored.status == "finished"

            # ---- Early-end proposal: accepted, result uses the current state.
            created_finish = await client.post(
                "/api/duels",
                json={"categories": ["movie"], "genres": []},
                headers=admin_headers,
            )
            assert created_finish.status_code == 201, created_finish.text
            finish_match_id = created_finish.json()["id"]
            finish_code = created_finish.json()["code"]
            assert len(finish_code) == 4 and finish_code.isdigit()
            finish_joined = await client2.post(
                "/api/duels/join",
                json={"code": finish_code},
                headers=second_headers,
            )
            assert finish_joined.status_code == 200, finish_joined.text

            finish_proposal = await client.post(
                f"/api/duels/{finish_match_id}/proposal",
                json={"type": "finish"},
                headers=admin_headers,
            )
            assert finish_proposal.status_code == 200, finish_proposal.text
            assert finish_proposal.json()["proposal"]["type"] == "finish"
            finish_response = await client2.post(
                f"/api/duels/{finish_match_id}/proposal/respond",
                json={"accept": True},
                headers=second_headers,
            )
            assert finish_response.status_code == 200, finish_response.text
            finish_state = finish_response.json()
            assert finish_state["phase"] == "finished"
            assert finish_state["status"] == "finished"
            assert finish_state["result"]["reason"] == "early_end"
            assert finish_state["result"]["draw"] is True
            assert finish_state["result"]["ranked"] is True

            board_after_finish = (
                await client.get("/api/leaderboard/duel")
            ).json()["entries"]
            assert len(board_after_finish) == 2
            stats_after_finish = {
                entry["user_id"]: (entry["wins"], entry["games"])
                for entry in board_after_finish
            }

            # ---- Cancel proposal: accepted, draw and excluded from the ranking.
            created_cancel = await client.post(
                "/api/duels",
                json={"categories": ["movie"], "genres": []},
                headers=admin_headers,
            )
            assert created_cancel.status_code == 201, created_cancel.text
            cancel_match_id = created_cancel.json()["id"]
            cancel_joined = await client2.post(
                "/api/duels/join",
                json={"code": created_cancel.json()["code"]},
                headers=second_headers,
            )
            assert cancel_joined.status_code == 200, cancel_joined.text

            cancel_proposal = await client.post(
                f"/api/duels/{cancel_match_id}/proposal",
                json={"type": "cancel"},
                headers=admin_headers,
            )
            assert cancel_proposal.status_code == 200, cancel_proposal.text
            assert cancel_proposal.json()["proposal"]["type"] == "cancel"
            cancel_response = await client2.post(
                f"/api/duels/{cancel_match_id}/proposal/respond",
                json={"accept": True},
                headers=second_headers,
            )
            assert cancel_response.status_code == 200, cancel_response.text
            cancel_state = cancel_response.json()
            assert cancel_state["phase"] == "finished"
            assert cancel_state["status"] == "cancelled"
            assert cancel_state["result"]["cancelled"] is True
            assert cancel_state["result"]["ranked"] is False
            assert cancel_state["result"]["draw"] is True

            board_after_cancel = (
                await client.get("/api/leaderboard/duel")
            ).json()["entries"]
            stats_after_cancel = {
                entry["user_id"]: (entry["wins"], entry["games"])
                for entry in board_after_cancel
            }
            assert stats_after_cancel == stats_after_finish

            # ---- Abandon: the opponent wins immediately.
            created_abandon = await client.post(
                "/api/duels",
                json={"categories": ["movie"], "genres": []},
                headers=admin_headers,
            )
            assert created_abandon.status_code == 201, created_abandon.text
            abandon_match_id = created_abandon.json()["id"]
            abandon_joined = await client2.post(
                "/api/duels/join",
                json={"code": created_abandon.json()["code"]},
                headers=second_headers,
            )
            assert abandon_joined.status_code == 200, abandon_joined.text
            abandoned = await client.post(
                f"/api/duels/{abandon_match_id}/abandon",
                headers=admin_headers,
            )
            assert abandoned.status_code == 200, abandoned.text
            abandon_state = abandoned.json()
            assert abandon_state["phase"] == "finished"
            assert abandon_state["status"] == "finished"
            assert abandon_state["result"]["reason"] == "abandon"
            assert abandon_state["result"]["winner_id"] == second_user_id
            assert abandon_state["result"]["ranked"] is True

            # ---- Timers: no more guesses after the personal deadline, and the
            # result is produced once every player is out of time.
            from app.db.models import DuelParticipant

            created_timer = await client.post(
                "/api/duels",
                json={"categories": ["movie"], "genres": []},
                headers=admin_headers,
            )
            assert created_timer.status_code == 201, created_timer.text
            timer_match_id = created_timer.json()["id"]
            timer_joined = await client2.post(
                "/api/duels/join",
                json={"code": created_timer.json()["code"]},
                headers=second_headers,
            )
            assert timer_joined.status_code == 200, timer_joined.text
            timer_state = timer_joined.json()
            for _ in range(12):
                first_roll = await client.post(
                    f"/api/duels/{timer_match_id}/roll", headers=admin_headers
                )
                second_roll = await client2.post(
                    f"/api/duels/{timer_match_id}/roll", headers=second_headers
                )
                assert first_roll.status_code == 200, first_roll.text
                assert second_roll.status_code == 200, second_roll.text
                timer_state = second_roll.json()
                if timer_state["phase"] == "settings":
                    break
            assert timer_state["phase"] == "settings"
            timer_setter_client = (
                client
                if timer_state["settings_setter_id"] == admin_user["id"]
                else client2
            )
            timer_setter_headers = (
                admin_headers
                if timer_state["settings_setter_id"] == admin_user["id"]
                else second_headers
            )
            timer_configured = await timer_setter_client.post(
                f"/api/duels/{timer_match_id}/settings",
                json={"exchange_count": 0, "duration_seconds": 300},
                headers=timer_setter_headers,
            )
            assert timer_configured.status_code == 200, timer_configured.text
            assert timer_configured.json()["phase"] == "playing"

            timer_playing = (
                await client.get(f"/api/duels/{timer_match_id}")
            ).json()
            timer_frame = timer_playing["frames"][0]["id"]
            async with session_factory() as db:
                participants = (
                    await db.execute(
                        select(DuelParticipant).where(
                            DuelParticipant.match_id == timer_match_id
                        )
                    )
                ).scalars().all()
                for participant in participants:
                    if participant.user_id == admin_user["id"]:
                        participant.time_penalty_seconds = 300
                await db.commit()

            timed_state = (
                await client.get(f"/api/duels/{timer_match_id}")
            ).json()
            assert timed_state["phase"] == "playing"
            assert timed_state["you"]["timed_out"] is True
            assert timed_state["opponent"]["timed_out"] is False
            assert timed_state["you"]["remaining_seconds"] == 0
            assert timed_state["opponent"]["remaining_seconds"] > 0

            late_guess = await client.post(
                f"/api/duels/{timer_match_id}/frames/{timer_frame}/guess",
                json={"guess": "Film Duel 0"},
                headers=admin_headers,
            )
            assert late_guess.status_code == 409
            assert late_guess.json()["error"]["code"] == "DUEL_TIME_UP"

            async with session_factory() as db:
                participants = (
                    await db.execute(
                        select(DuelParticipant).where(
                            DuelParticipant.match_id == timer_match_id
                        )
                    )
                ).scalars().all()
                for participant in participants:
                    participant.time_penalty_seconds = 300
                await db.commit()

            timer_finished = (
                await client.get(f"/api/duels/{timer_match_id}")
            ).json()
            assert timer_finished["phase"] == "finished"
            assert timer_finished["result"]["reason"] == "time"
            assert timer_finished["result"]["ranked"] is True


def test_media_payload_clips_postgresql_varchar_fields() -> None:
    from app.emby.sync import _build_media_payload

    item = _movie_payload()
    item["ImageTags"]["Primary"] = "p" * 600
    item["Etag"] = "e" * 400
    item["Name"] = "T" * 900
    payload = _build_media_payload(
        item,
        library_id=1,
        server_id="server1",
        series_map={},
    )
    assert payload is not None
    assert len(payload["poster_tag"]) == 512
    assert len(payload["emby_etag"]) == 255
    assert len(payload["title"]) == 512
    assert len(payload["search_text"]) <= 1024


async def test_profile_customization(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    from io import BytesIO

    from PIL import Image

    with respx.mock(assert_all_called=False) as mock:
        _register_emby(mock)
        csrf, _ = await _setup_and_login(client, monkeypatch)
        mock.get(f"{EMBY}/Items").mock(
            return_value=httpx.Response(
                200, json={"Items": [_movie_payload()], "TotalRecordCount": 1}
            )
        )
        await run_catalog_sync("test", session_factory)
        headers = {"X-CSRF-Token": csrf}

        updated = await client.put(
            "/api/users/me/profile",
            json={"display_name": "Matty"},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["display_name"] == "Matty"
        me = await client.get("/api/auth/me")
        assert me.json()["user"]["display_name"] == "Matty"

        search = await client.get("/api/users/me/showcase/search?q=incep")
        assert search.status_code == 200, search.text
        items = search.json()["items"]
        assert items and items[0]["title"] == "Inception"
        media_id = items[0]["media_id"]

        showcase = await client.put(
            "/api/users/me/showcase",
            json={"media_ids": [media_id]},
            headers=headers,
        )
        assert showcase.status_code == 200, showcase.text
        assert len(showcase.json()["items"]) == 1
        assert (await client.get("/api/users/me/showcase")).json()["items"][0][
            "media_id"
        ] == media_id

        too_many = await client.put(
            "/api/users/me/showcase",
            json={"media_ids": [media_id] * 6},
            headers=headers,
        )
        assert too_many.status_code == 422

        image = BytesIO()
        Image.new("RGB", (64, 64), "red").save(image, format="JPEG")
        uploaded = await client.post(
            "/api/users/me/avatar",
            files={"avatar": ("avatar.jpg", image.getvalue(), "image/jpeg")},
            headers=headers,
        )
        assert uploaded.status_code == 200, uploaded.text
        avatar_url = uploaded.json()["avatar_url"]
        assert avatar_url
        avatar = await client.get("/api/users/me/avatar")
        assert avatar.status_code == 200
        assert avatar.headers["content-type"].startswith("image/jpeg")

        removed = await client.delete("/api/users/me/avatar", headers=headers)
        assert removed.status_code == 200, removed.text
        assert removed.json()["avatar_url"] is None


async def test_unauthenticated_admin_route_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/admin/sync/status")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
