"""Real captures plus explicitly synthetic structure, selection and recovery cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, DataFormat, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.nishitetsu import NishitetsuProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://jik.nishitetsu.jp/traffic/default.htm"
_GROUP = "天神大牟田線（太宰府線・甘木線含む）"
_EMPTY = "台風や大雪などの時に当社バス・電車の運行状況をお知らせいたします。"


def _page(panel: str) -> bytes:
    return (f'<html><body><img src="tit_unkou.jpg" alt="運行状況">'
            f'<div class="traffic">{panel}</div><table><tr><td>links</td></tr></table>'
            '</body></html>').encode()


async def _refresh(body: bytes) -> NishitetsuProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NishitetsuProvider(client=client)
        await provider.refresh()
        assert not client.is_closed
        return provider


@pytest.mark.parametrize("filename", [
    "nishitetsu_normal.html", "nishitetsu_20241003190025.html", "nishitetsu_20260817152210.html",
])
def test_real_no_railway_notices(filename: str) -> None:
    provider = asyncio.run(_refresh((_FIXTURES / filename).read_bytes()))
    assert len(provider.lines) == 4
    assert all(line.status is LineStatus.NORMAL and not line.alerts for line in provider.lines)


def test_real_group_notice_preserves_text_without_inferred_impact() -> None:
    provider = asyncio.run(_refresh((_FIXTURES / "nishitetsu_20260728135357.html").read_bytes()))
    assert all(line.status is LineStatus.ALERT for line in provider.lines[:3])
    assert provider.kaizuka.status is LineStatus.NORMAL
    alert, = provider.alerts
    assert alert.title == _GROUP and "<地震によるダイヤ乱れ>" in alert.description
    assert "https://busnavi-railway.nnr.co.jp/tenjin_omuta/" in alert.description
    assert alert.effect is AlertEffect.OTHER and alert.timing is AlertTiming.UNKNOWN
    assert alert.affected_line_ids == ()
    assert provider.active_alerts == () and provider.delay_lines == ()
    assert all(line.updated_at is None for line in provider.lines)
    assert provider.tenjin_omuta.fetched_at is not None
    assert provider.tenjin_omuta.fetched_at.utcoffset() == timedelta(0)


def test_real_restoration_notice_is_still_an_announcement() -> None:
    provider = asyncio.run(_refresh((_FIXTURES / "nishitetsu_20240124024435.html").read_bytes()))
    assert provider.tenjin_omuta.status is LineStatus.ALERT
    assert provider.alerts[0].timing is AlertTiming.UNKNOWN


def test_real_kaizuka_heading_and_unclassified_heading() -> None:
    provider = asyncio.run(_refresh((_FIXTURES / "nishitetsu_20240829221823.html").read_bytes()))
    # This capture also has a generic 運行状況 heading. Do not guess from its bus prose.
    assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
    kaizuka = next(a for a in provider.kaizuka.alerts if a.title == "貝塚線")
    assert kaizuka.affected_line_ids == (provider.kaizuka.line_id,)
    assert kaizuka.effect is AlertEffect.OTHER
    assert any(a.affected_line_ids == () for a in provider.kaizuka.alerts)


@pytest.mark.parametrize("text", [
    "合成：運休は発生していません。", "合成：明日の運転を見合わせる予定です。",
    "合成：運転を再開しました。", "合成：一部区間で遅延しています。",
])
def test_synthetic_prose_never_sets_disruption_or_timing(text: str) -> None:
    provider = asyncio.run(_refresh(_page(f'<h3>{_GROUP}</h3><p>{text}</p>')))
    assert provider.tenjin_omuta.status is LineStatus.ALERT
    assert provider.kaizuka.status is LineStatus.NORMAL
    alert, = provider.alerts
    assert alert.description == text and alert.timing is AlertTiming.UNKNOWN
    assert alert.active_from is None and alert.active_until is None
    assert alert.affected_line_ids == ()


def test_synthetic_unknown_heading_keeps_notice_and_unknown_targets() -> None:
    provider = asyncio.run(_refresh(_page('<h3>合成：新しい掲載単位</h3><p>合成案内</p>')))
    assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
    alert, = provider.alerts
    assert alert.description == "合成案内" and alert.affected_line_ids == ()
    assert alert.effect is AlertEffect.UNKNOWN


def test_synthetic_bus_bodies_are_outside_railway_scope() -> None:
    provider = asyncio.run(_refresh(_page(
        '<h3>高速バス</h3><p><a>合成：貝塚線運休に言及</a><script>1</script></p>'
        '<h3>一般路線バス</h3><p></p>',
    )))
    assert all(line.status is LineStatus.NORMAL for line in provider.lines)
    assert provider.alerts == ()


def test_synthetic_kaizuka_notice_does_not_affect_other_lines() -> None:
    provider = asyncio.run(_refresh(_page('<h3>貝塚線</h3><p>合成：運行案内</p>')))
    assert all(line.status is LineStatus.NORMAL for line in provider.lines[:3])
    assert provider.kaizuka.status is LineStatus.ALERT
    alert, = provider.alerts
    assert alert.affected_line_ids == (provider.kaizuka.line_id,)


@pytest.mark.parametrize("panel", [
    "", "合成：見慣れない平常文", "<h3>貝塚線</h3>", "<h3>貝塚線</h3><p></p>",
    "<h3>貝塚線</h3><p>合成</p><h3>貝塚線</h3><p>重複</p>",
    '<h3>貝塚線</h3><p><script>1</script>合成</p>',
    '<h3>貝塚線</h3><p><a>合成</a></p>',
    '<h3>貝塚線</h3><p><a href="javascript:void(0)">合成</a></p>',
])
def test_synthetic_malformed_notice_keeps_previous_snapshot(panel: str) -> None:
    async def scenario() -> None:
        body = _page(f"<h3>{_GROUP}</h3><p>合成案内</p>")
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body),
        )) as client:
            provider = NishitetsuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            body = _page(panel)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_title", "truncated"])
def test_synthetic_page_damage_is_not_normal(mutation: str) -> None:
    page = _page(_EMPTY).decode()
    if mutation == "missing":
        page = page.replace('class="traffic"', 'class="removed"')
    elif mutation == "duplicate":
        page = page.replace('</body>', '<div class="traffic">' + _EMPTY + '</div></body>')
    elif mutation == "wrong_title":
        page = page.replace('alt="運行状況"', 'alt="合成メンテナンス"')
    else:
        page = page.split('<table>')[0]
    with pytest.raises(ParseError):
        asyncio.run(_refresh(page.encode()))


def test_synthetic_clearing_and_tracker_failure_isolation() -> None:
    async def scenario() -> None:
        body = _page(f"<h3>{_GROUP}</h3><p>合成案内</p>")
        code = 200
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(code, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NishitetsuProvider(client=client)
            disabled = Tracker(enabled_providers=(), client=client, overrides=(provider,))
            await disabled.refresh()
            assert not calls
            tracker = Tracker(enabled_providers=("nishitetsu", "kyoto_subway"), client=client,
                              overrides=(provider,))
            # Other source fails parsing; Nishitetsu still updates.
            with pytest.raises(RefreshError) as caught:
                await tracker.refresh()
            assert set(caught.value.errors) == {ProviderId("kyoto_subway")}
            assert tracker.nishitetsu is provider and provider.alerts
            body = _page(_EMPTY)
            await provider.refresh()
            assert provider.alerts == () and all(l.status is LineStatus.NORMAL for l in provider.lines)
            previous = provider.lines
            code = 503
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_shared_ids_default_registration_and_independent_snapshots() -> None:
    tracker = Tracker()
    provider = tracker.nishitetsu
    assert provider in tracker.providers
    assert provider.lines == (provider.tenjin_omuta, provider.dazaifu, provider.amagi, provider.kaizuka)
    assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
    for line in provider.lines:
        yahoo = tracker.yahoo.get_line(line.line_id)
        assert yahoo is not None and yahoo is not line
        assert line.operator == yahoo.operator and line.operator.name == "西日本鉄道"
    metadata = provider.metadata
    assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(metadata.source_page_url) == _URL
    assert str(metadata.terms_url) == "https://www.nishitetsu.jp/nnr/site-kitei/"
    endpoint, = metadata.endpoints
    assert endpoint.url == _URL and endpoint.method == "GET" and endpoint.format is DataFormat.HTML
