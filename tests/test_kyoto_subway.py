"""Real Kyoto emergency/cleared captures; other markup below is explicitly synthetic."""

import asyncio
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.kyoto_subway import KyotoSubwayProvider
from train_operation_info.providers.yahoo import YahooRouteId

_FIXTURES = Path(__file__).parent / "fixtures"
_START = "<!-- ▼▼緊急情報▼▼ -->"
_END = "<!-- ▲▲緊急情報▲▲ -->"


def _synthetic(region: str = "") -> str:
    return (
        '<html><body class="ku_top"><div id="main">'
        f'{_START}{region}{_END}<div id="main_lower">'
        '通常のお知らせ：東西線は運休予定</div></div><div id="foot"></div></body></html>'
    )


def _synthetic_notice(text: str) -> str:
    return (
        '<div id="imp" class="imp_kinkyu"><h2><img alt="緊急情報"></h2>'
        f'<div class="imp_lower"><div class="imp_kinkyu_lower">{text}</div></div></div>'
    )


@pytest.mark.parametrize(("fixture", "expected"), [
    ("kyoto_subway_normal.html", LineStatus.NORMAL),
    ("kyoto_subway_notice_20230815040858.html", LineStatus.UNKNOWN),
    ("kyoto_subway_cleared_20230816075536.html", LineStatus.NORMAL),
])
def test_real_captures_and_shared_yahoo_identity(fixture: str, expected: LineStatus) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://www.city.kyoto.lg.jp/kotsu/"
            assert request.headers["User-Agent"] == USER_AGENT
            return httpx.Response(200, content=(_FIXTURES / fixture).read_bytes())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("kyoto_subway",), client=client)
            provider = tracker.kyoto_subway
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            await tracker.refresh()
            assert not client.is_closed
            assert tracker.lines == provider.lines == (provider.karasuma, provider.tozai)
            for route_id, line in zip(("318/0", "319/0"), provider.lines):
                yahoo = tracker.yahoo.get_source_line(YahooRouteId(route_id))
                assert yahoo is not None and yahoo.line_id == line.line_id
                assert yahoo.operator is line.operator
                assert yahoo is not line and yahoo.fetched_at is None
                assert line.status is expected
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            if expected is LineStatus.NORMAL:
                assert not provider.alerts
            else:
                alert, = provider.alerts
                assert alert.affected_line_ids == ()
                assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None
                assert "0000316308.html" in alert.description
                assert "0000316290.html" in alert.description  # Bus notice is not a subway suspension.
                assert not provider.active_alerts

    asyncio.run(scenario())


def test_real_notice_then_cleared_panel_removes_alerts() -> None:
    async def scenario() -> None:
        fixtures = iter(("kyoto_subway_notice_20230815040858.html",
                         "kyoto_subway_cleared_20230816075536.html", "kyoto_subway_normal.html"))
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=(_FIXTURES / next(fixtures)).read_bytes()),
        )) as client:
            provider = KyotoSubwayProvider(client=client)
            await provider.refresh()
            assert provider.alerts
            for _ in range(2):
                await provider.refresh()
                assert not provider.alerts
                assert all(line.status is LineStatus.NORMAL for line in provider.lines)

    asyncio.run(scenario())


@pytest.mark.parametrize("text", [
    "烏丸線は運転見合わせ。東西線は平常運転。",  # No structured route/effect fields.
    "過去の運転見合わせは解消しました。",
    "来月は地下鉄を運休する予定です。",
    "市バスのみ運休中。地下鉄に遅延はありません。",
    "確認したことのない新しい状態です。",
])
def test_synthetic_narrative_never_establishes_route_effect_or_timing(text: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=_synthetic(_synthetic_notice(text))),
        )) as client:
            provider = KyotoSubwayProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            alert, = provider.alerts
            assert alert.description == text and alert.affected_line_ids == ()
            assert alert.timing is AlertTiming.UNKNOWN and alert.effect is AlertEffect.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", [
    "unrelated successful HTML",
    _synthetic().replace(_START, ""),
    _synthetic().replace(_END, ""),
    _synthetic().replace(_START, _START + _START),
    _synthetic().replace(_START, _END).replace(_END + _END, _END + _START),
    _synthetic().replace('<div id="foot"></div>', ""),
    _synthetic().replace(_START, '<div>' + _START).replace(_END, _END + '</div>'),
    _synthetic().replace(_END, _END + '<div id="imp"></div>'),
    _synthetic('<div id="imp"></div>'),
    _synthetic(_synthetic_notice("")),
    _synthetic(_synthetic_notice('本文<script>fetch("status.json")</script>')),
    _synthetic(_synthetic_notice('<a>詳細</a>')),
    _synthetic(_synthetic_notice('<a href="javascript:alert(1)">詳細</a>')),
    _synthetic(_synthetic_notice("本文") + _synthetic_notice("本文")),
])
def test_synthetic_bad_structure_preserves_complete_snapshot(broken: str) -> None:
    async def scenario() -> None:
        responses = iter((_synthetic(_synthetic_notice("案内")), broken))
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=next(responses)),
        )) as client:
            provider = KyotoSubwayProvider(client=client)
            await provider.refresh()
            original = provider.lines
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is original

    asyncio.run(scenario())


def test_synthetic_http_failure_and_default_registration() -> None:
    async def scenario() -> None:
        status = 200
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text=_synthetic()),
        )) as client:
            provider = KyotoSubwayProvider(client=client)
            assert "kyoto_subway" in {p.provider_id for p in Tracker().providers}
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            original = provider.lines
            status = 503
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is original

    asyncio.run(scenario())
