"""Real normal/out-of-hours responses and explicitly synthetic incident cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, LineId, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.yurikamome import YurikamomeProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_FEED = "https://cms-2.yurikamome.co.jp/api/operation/"


def _html(name: str = "normal") -> str:
    return (_FIXTURES / f"yurikamome_{name}.html").read_text(encoding="utf-8")


def _synthetic(label: str, body: str = "合成テスト：新橋～豊洲間の運行案内。") -> str:
    """Use the real feed structure without claiming this incident occurred."""
    soup = BeautifulSoup(_html(), "html.parser")
    title = soup.select_one(".info_title")
    text = soup.select_one(".info_text")
    assert title is not None and text is not None
    title.clear()
    title.append(label)
    text.string = f"[運行状況] {body}"
    return str(soup)


def test_official_normal_and_out_of_hours() -> None:
    html = _html()

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            tracker = Tracker(enabled_providers=("yurikamome",), client=client)
            provider = tracker.yurikamome
            assert provider.unknown_lines == (provider.main,)
            await tracker.refresh()
            line = provider.main
            assert line.line_id == LineId("jp:operator_c0a210bf19c5:line_cbfd3a81aaf1")
            assert line.name == "ゆりかもめ線" and line.operator.name == "ゆりかもめ"
            assert line.provider_id == ProviderId("yurikamome")
            assert line.source_url == "https://www.yurikamome.co.jp/ride-guidance/operation.html"
            assert line.status is LineStatus.NORMAL and line.source_status == "平常運転"
            assert line.updated_at is not None
            assert line.updated_at.isoformat() == "2026-11-02T04:00:00+09:00"
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert not provider.alerts
            html = _html("20191003184453")
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.alerts[0].effect is AlertEffect.UNKNOWN
            assert "情報提供時間" in provider.alerts[0].description
            assert provider.main.updated_at is not None
            assert provider.main.updated_at.isoformat() == "2019-10-04T02:00:00+09:00"
            assert not client.is_closed
    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "expected"), [
    ("遅延", LineStatus.DELAYED),
    ("運転見合わせ", LineStatus.SUSPENDED),
    ("運転再開見込", LineStatus.SUSPENDED),
    ("運休", LineStatus.SUSPENDED),
    ("一部運休", LineStatus.PARTIAL_SUSPENSION),
    ("折返し運転", LineStatus.PARTIAL_SUSPENSION),
    ("一部運転再開", LineStatus.PARTIAL_SUSPENSION),
    ("運転再開", LineStatus.ALERT),
    ("直通運転再開", LineStatus.ALERT),
    ("バス代行", LineStatus.ALERT),
    ("経路変更", LineStatus.ALERT),
    ("リフレッシュ工事", LineStatus.ALERT),
    ("お知らせ", LineStatus.ALERT),
    ("直通運転中止", LineStatus.ALERT),
    ("お詫び", LineStatus.ALERT),
    ("自由文", LineStatus.ALERT),
    ("振替輸送", LineStatus.ALERT),
    ("合成の未知状態", LineStatus.UNKNOWN),
    ("平常運転", LineStatus.UNKNOWN),  # Contradictory body must not clear an incident.
])
def test_synthetic_labels_and_recovery(label: str, expected: LineStatus) -> None:
    body = "合成テスト：以前は運転見合わせ、遅延が発生していました。\n新橋～豊洲間の案内です。"
    html = _synthetic(label, body)

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = YurikamomeProvider(client=client)
            await provider.refresh()
            previous = provider.main
            assert previous.status is expected and previous.source_status == label
            alert, = provider.alerts
            assert alert.title == label and alert.description == body
            assert alert.affected_line_ids == (previous.line_id,)
            assert provider.delay_lines == ((previous,) if expected is LineStatus.DELAYED else ())
            html = _html()
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.affected_lines and not provider.unknown_lines
            assert previous.status is expected and previous.alerts == (alert,)
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "missing_title", "duplicate_title", "empty_title",
    "missing_body", "duplicate_body", "empty_body", "prefix_only", "missing_time",
    "duplicate_time", "invalid_time", "invalid_date", "placeholder",
])
def test_synthetic_malformed_feed_preserves_previous_incident(mutation: str) -> None:
    html = _synthetic("運転見合わせ")
    soup = BeautifulSoup(html, "html.parser")
    selector = {
        "panel": "aside.info", "title": ".info_title", "body": ".info_text", "time": ".info_update",
    }
    if mutation == "placeholder":
        malformed = '<aside class="info"><h2 class="info_title">-</h2></aside>'
    else:
        action, field = mutation.split("_", 1)
        target = soup.select_one(selector.get(field, ".info_update"))
        assert target is not None
        if action == "missing":
            target.decompose()
        elif action == "duplicate":
            target.insert_after(BeautifulSoup(str(target), "html.parser"))
        elif action == "empty":
            target.clear()
        elif mutation == "prefix_only":
            target = soup.select_one(".info_text")
            assert target is not None
            target.string = "[運行状況] "
        else:
            target.string = "2026年13月2日4時0分 配信" if field == "date" else "04:00"
        malformed = str(soup)

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = YurikamomeProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = malformed
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
    asyncio.run(scenario())


def test_transport_failure_isolated_and_selection_respected() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _FEED:
            return httpx.Response(503)
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, text=(_FIXTURES / "hankyu_normal.html").read_text(encoding="utf-8"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YurikamomeProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _FEED not in requests
            tracker = Tracker(enabled_providers=("yurikamome", "hankyu"), client=client, overrides=(provider,))
            assert tracker.yurikamome is provider and tracker.providers[0] is provider
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("yurikamome")}
            assert isinstance(captured.value.errors[ProviderId("yurikamome")], FetchError)
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
            assert provider.main.status is LineStatus.UNKNOWN
    asyncio.run(scenario())


def test_shared_canonical_route_and_reviewed_metadata() -> None:
    tracker = Tracker()
    provider = tracker.yurikamome
    assert provider in tracker.providers
    official = provider.main
    yahoo = tracker.yahoo.get_line(official.line_id)
    assert yahoo is not None and official is not yahoo
    assert official.operator == yahoo.operator
    metadata = provider.metadata
    assert metadata.usage_permission is UsagePermission.PRIVATE_USE_ONLY
    assert metadata.reviewed_at.utcoffset() == timedelta(0)
    assert str(metadata.terms_url) == "https://www.yurikamome.co.jp/utility/policy.html"
