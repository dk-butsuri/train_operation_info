"""Live normal capture; all incident and malformed pages below are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertTiming, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.sapporo_subway import SapporoSubwayProvider

_URL = "https://operationstatus.city.sapporo.jp/unkojoho/"
_NORMAL = "現在、10分以上の遅れは発生していません。"


def _synthetic(status: str = _NORMAL, extra: str = "") -> str:
    return (
        '<div id="tmp_contents"><h1 class="home">運行情報</h1>'
        f'<div class="line">南北線</div><h2 class="status">{status}</h2>{extra}'
        f'<div class="line">東西線</div><h2 class="status">{_NORMAL}</h2>'
        f'<div class="line">東豊線</div><h2 class="status">{_NORMAL}</h2>'
        '<ul><li>運行情報の詳細は、<a href="rireki_all.html">運行情報履歴</a></li></ul>'
        '<p>対象外のフッター</p></div>'
    )


def test_live_normal_routes_metadata_and_yahoo_identity() -> None:
    content = (Path(__file__).parent / "fixtures/sapporo_subway_normal.html").read_bytes()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.method == "GET" and request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=content)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("sapporo_subway",), client=client)
            provider = tracker.sapporo_subway
            assert len(provider.unknown_lines) == 3
            await tracker.refresh()
            assert requests == [_URL]
            assert provider.lines == (provider.namboku, provider.tozai, provider.toho)
            assert not provider.alerts
            for line, name in zip(provider.lines, ("南北線", "東西線", "東豊線")):
                assert line.status is LineStatus.NORMAL and line.source_status == _NORMAL
                assert line.source_line_names == (name,)
                assert line.updated_at is None and line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                assert line.operator.name == "札幌市交通局"
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo is not line
                assert yahoo.operator == line.operator and yahoo.status is LineStatus.UNKNOWN
            assert not client.is_closed
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert str(provider.metadata.source_page_url) == _URL
            assert str(provider.metadata.terms_url) == "https://www.city.sapporo.jp/city/copyright/link.html"
        assert ProviderId("sapporo_subway") in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())


@pytest.mark.parametrize(("status", "extra"), [
    ("合成：運転見合わせ", "<p>明日実施する案内。以前は遅延。</p>"),
    ("遅れ", ""),  # A history label is not a verified current-page vocabulary.
    ("平常運転", ""),
    (_NORMAL, "<p>合成：追加の案内。</p>"),
    (_NORMAL + "合成：補足", ""),
])
def test_synthetic_notices_remain_unknown_and_recovery_clears_alerts(status: str, extra: str) -> None:
    content = _synthetic(status, extra)

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=content),
        )) as client:
            provider = SapporoSubwayProvider(client=client)
            tracker = Tracker(enabled_providers=("sapporo_subway",), overrides=(provider,))
            assert tracker.sapporo_subway is provider
            await tracker.refresh()
            line = provider.namboku
            assert line.status is LineStatus.UNKNOWN
            assert provider.tozai.status is provider.toho.status is LineStatus.NORMAL
            assert not tracker.affected_lines and not tracker.active_alerts
            alert, = tracker.unclassified_alerts
            assert alert.timing is AlertTiming.UNKNOWN
            assert alert.affected_line_ids == (line.line_id,)
            assert status in alert.description
            if extra:
                assert "案内。" in alert.description
            assert alert.active_from is None and alert.active_until is None
            assert line.updated_at is None
            content = _synthetic()
            await tracker.refresh()
            assert not provider.alerts and not tracker.unknown_lines

    asyncio.run(scenario())


@pytest.mark.parametrize(("old", "new"), [
    ('<div class="line">南北線</div>', ""),
    ('南北線', '東西線'),
    ('南北線', '未知の路線'),
    ('<h2 class="status">' + _NORMAL + '</h2>', ''),
    ('<h2 class="status">' + _NORMAL + '</h2>', '<h2 class="status"></h2>'),
    ('<h2 class="status">', '<h2>'),
    ('<h1 class="home">運行情報</h1>', '<h1 class="home">運行情報履歴</h1>'),
    ('id="tmp_contents"', 'id="changed"'),
    ('href="rireki_all.html"', 'href="changed.html"'),
    ('<div class="line">南北線</div>', '<div class="line">南北線</div><div class="line">南北線</div>'),
])
def test_synthetic_structure_errors_preserve_snapshot(old: str, new: str) -> None:
    content = _synthetic("合成：案内あり")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=content),
        )) as client:
            provider = SapporoSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            content = _synthetic().replace(old, new, 1)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_disabled_selection_and_fetch_failure_preserve_state() -> None:
    fail = False
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(503 if fail else 200, text=_synthetic())

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SapporoSubwayProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not requests
            tracker = Tracker(enabled_providers=("sapporo_subway",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert isinstance(captured.value.errors[ProviderId("sapporo_subway")], FetchError)
            assert provider.lines is previous

    asyncio.run(scenario())
