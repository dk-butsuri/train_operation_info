"""Real normal/plan captures and explicitly synthetic validation/recovery cases."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.fukuoka_subway import FukuokaSubwayProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://subway.city.fukuoka.lg.jp/status/"
_NORMAL = "通常運行しています。"


def _page(text: str = _NORMAL, stamp: str = "") -> bytes:
    return (
        '<html><body><section id="status"><h2 class="ttl_h2">運行情報</h2>'
        '<div class="box box02"><div class="data">2099年01月01日 00時00分 現在</div>'
        f'<dl><dt><span class="status st02"></span><div class="statusNews">{text}</div>'
        f'<div align="right">{stamp}</div></dt><dd>合成：掲載条件</dd></dl></div>'
        '</section><footer>合成フッター</footer></body></html>'
    ).encode()


async def _refresh(body: bytes) -> FukuokaSubwayProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL and request.method == "GET"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FukuokaSubwayProvider(client=client)
        await provider.refresh()
        assert not client.is_closed
        return provider


@pytest.mark.parametrize("filename", [
    "fukuoka_subway_normal.html", "fukuoka_subway_20230711012832.html",
    "fukuoka_subway_20241224075857.html", "fukuoka_subway_20250501031503.html",
    "fukuoka_subway_20260527005254.html",
])
def test_real_normal_pages_have_no_publication_time(filename: str) -> None:
    provider = asyncio.run(_refresh((_FIXTURES / filename).read_bytes()))
    assert len(provider.lines) == 3
    assert all(line.status is LineStatus.NORMAL for line in provider.lines)
    assert all(line.updated_at is None for line in provider.lines)
    assert provider.alerts == ()


def test_real_suspension_plan_is_not_an_active_suspension() -> None:
    provider = asyncio.run(_refresh((_FIXTURES / "fukuoka_subway_20240829161647.html").read_bytes()))
    assert all(line.status is LineStatus.ALERT for line in provider.lines)
    alert, = provider.alerts
    assert "始発から運転を見合わせます" in alert.description
    assert alert.affected_line_ids == ()
    assert alert.effect is AlertEffect.OTHER and alert.timing is AlertTiming.UNKNOWN
    assert alert.active_from is None and alert.active_until is None
    assert provider.active_alerts == () and provider.delay_lines == ()
    assert provider.kuko.updated_at == datetime.fromisoformat("2024-08-30T00:00:00+09:00")
    assert provider.kuko.fetched_at is not None
    assert provider.kuko.fetched_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", [
    "合成：七隈線で遅延しています。", "合成：空港線の運休は発生していません。",
    "合成：明日から全線を運休します。", "合成：通常運行に戻りました。",
    "通常運行しています。合成：ただし一部に案内があります。",
])
def test_synthetic_prose_never_infers_routes_effect_or_timing(text: str) -> None:
    provider = asyncio.run(_refresh(_page(text)))
    assert all(line.status is LineStatus.ALERT for line in provider.lines)
    alert, = provider.alerts
    assert alert.description == text and alert.affected_line_ids == ()
    assert alert.timing is AlertTiming.UNKNOWN and alert.effect is AlertEffect.OTHER
    assert all(line.updated_at is None for line in provider.lines)


def test_synthetic_links_preserved_and_separate_header_ignored() -> None:
    page = _page('合成：<a href="/notice/example.html">ご案内</a>').replace(
        b'<section', '<div id="suspension">合成：計画運休</div><section'.encode(),
    )
    provider = asyncio.run(_refresh(page))
    assert "https://subway.city.fukuoka.lg.jp/notice/example.html" in provider.alerts[0].description
    normal = asyncio.run(_refresh(_page().replace(
        b'<section', '<div id="suspension">合成：計画運休</div><section'.encode(),
    )))
    assert normal.alerts == () and all(line.status is LineStatus.NORMAL for line in normal.lines)


@pytest.mark.parametrize("broken", [
    _page(""), _page("合成", "2026年11月04日 12時00分 現在"),
    _page("合成", "2026年02月30日 12時00分 更新"),
    _page('<a>合成</a>'), _page('<a href="javascript:void(0)">合成</a>'),
    _page('<script>1</script>合成'),
    _page().replace(b'class="statusNews"', b'class="missing"'),
    _page().replace(b'</dt>', b'<div class="statusNews">duplicate</div></dt>'),
    _page().replace(b'</dt>', b'extra notice</dt>'),
    _page().replace(b'<footer>', b'<aside>').replace(b'</footer>', b'</aside>'),
    _page().replace('運行情報</h2>'.encode(), '合成：別ページ</h2>'.encode()),
])
def test_synthetic_bad_page_and_http_failure_keep_snapshot(broken: bytes) -> None:
    async def scenario() -> None:
        body, code = _page("合成案内"), 200
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(code, content=body),
        )) as client:
            provider = FukuokaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            body = broken
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            code = 503
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_clearing_selection_overrides_and_failure_isolation() -> None:
    async def scenario() -> None:
        body = _page("合成案内", "2026年11月04日 12時00分 更新")
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FukuokaSubwayProvider(client=client)
            disabled = Tracker(enabled_providers=(), client=client, overrides=(provider,))
            await disabled.refresh()
            assert not calls
            tracker = Tracker(enabled_providers=("fukuoka_subway", "kyoto_subway"),
                              client=client, overrides=(provider,))
            with pytest.raises(RefreshError) as caught:
                await tracker.refresh()
            assert set(caught.value.errors) == {ProviderId("kyoto_subway")}
            assert tracker.fukuoka_subway is provider and provider.alerts
            body = _page()
            await provider.refresh()
            assert provider.alerts == () and all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert all(line.updated_at is None for line in provider.lines)

    asyncio.run(scenario())


def test_existing_catalog_ids_default_registration_and_independent_snapshots() -> None:
    tracker = Tracker()
    provider = tracker.fukuoka_subway
    assert provider in tracker.providers
    assert provider.lines == (provider.kuko, provider.hakozaki, provider.nanakuma)
    assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
    for line in provider.lines:
        yahoo = tracker.yahoo.get_line(line.line_id)
        assert yahoo is not None and yahoo is not line
        assert yahoo.operator == line.operator and line.operator.name == "福岡市交通局"
    assert provider.metadata.usage_permission is UsagePermission.PRIVATE_USE_ONLY
    assert str(provider.metadata.terms_url) == "https://subway.city.fukuoka.lg.jp/utility/"
