"""Official Nankai captures; malformed/unknown cases are explicitly synthetic."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, LINE_CATALOG, LineId, LineStatus, ProviderId
from train_operation_info.providers.nankai import NankaiProvider
from train_operation_info.providers.nankai.provider import _parse_group
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"


def test_archived_delay_route_scope_and_source_time() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://www.traffic.nankai.co.jp/railinfo/01.html"
            return httpx.Response(200, content=(_FIXTURES / "nankai_20261004112434.html").read_bytes())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NankaiProvider(client=client)
            await provider.refresh()
            assert {line.line_id for line in provider.delay_lines} == {
                LineId("jp:nankai:koya"), LineId("jp:nankai:semboku"),
            }
            assert provider.cable.status is LineStatus.NORMAL
            assert provider.shiomibashi.status is LineStatus.NORMAL
            assert provider.koya.updated_at == datetime.fromisoformat("2026-10-04T20:15:00+09:00")
            assert provider.koya.fetched_at is not None
            assert provider.koya.fetched_at.utcoffset() == timedelta(0)
            assert provider.semboku.alerts[0].affected_line_ids == (provider.semboku.line_id,)
            # Koya is mentioned as the cause, not as this notice's target.
            assert "高野線堺東駅" in provider.semboku.alerts[0].description
            assert provider.semboku.alerts[0].effect is AlertEffect.DELAYS
            assert provider.main.operator.name == "南海電気鉄道"
            assert all(line.operator is LINE_CATALOG[line.line_id].operator for line in provider.lines)

    asyncio.run(scenario())


def test_special_train_notice_does_not_suspend_whole_route() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=(_FIXTURES / "nankai_20250806220111.html").read_bytes()),
        )) as client:
            provider = NankaiProvider(client=client)
            await provider.refresh()
            assert provider.semboku.status is LineStatus.DELAYED
            assert provider.koya.status is LineStatus.ALERT
            assert provider.koya.alerts[0].title == "泉北ライナー"
            assert provider.koya.alerts[0].affected_line_ids == ()
            assert len(provider.alerts) == 2
            assert provider.main.alerts == ()

    asyncio.run(scenario())


@pytest.mark.parametrize("group", ["nankai", "koya"])
def test_archived_suspension_sections_before_semboku_was_added(group: str) -> None:
    # The original has no Semboku section. Test its unchanged section DOM;
    # do not synthesize a new section and present it as archived evidence.
    soup = BeautifulSoup((_FIXTURES / "nankai_20230814234144.html").read_text(encoding="utf-8"), "html.parser")
    provider = NankaiProvider()
    lines = provider.lines[:6] if group == "nankai" else provider.lines[6:9]
    result = _parse_group(
        soup, group, lines, datetime.now(timezone.utc),
        datetime.fromisoformat("2023-08-15T05:54:00+09:00"),
    )
    assert all(line.status is LineStatus.SUSPENDED for line in result)
    for line in result:
        scoped = [alert for alert in line.alerts if alert.affected_line_ids]
        assert len(scoped) == 1
        assert scoped[0].affected_line_ids == (line.line_id,)
        assert scoped[0].effect is AlertEffect.NO_SERVICE
        assert "現在運転を見合せております。" in scoped[0].description


def test_tracker_selection_injection_and_clearing_old_alerts() -> None:
    fixture = "nankai_20261004112434.html"

    async def scenario() -> None:
        nonlocal fixture
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=(_FIXTURES / fixture).read_bytes()),
        )) as client:
            provider = NankaiProvider(client=client)
            tracker = Tracker(enabled_providers=("nankai",), overrides=(provider,))
            assert tracker.providers == (provider,)
            assert len(tracker.unknown_lines) == 10
            await tracker.refresh()
            old_line = tracker.nankai.koya
            delayed_before = tracker.delay_lines
            assert len(delayed_before) == 2
            fixture = "nankai_normal.html"
            await tracker.refresh()
            assert tracker.alerts == ()
            assert len(tracker.delay_lines) == 0
            assert all(line.status is LineStatus.NORMAL for line in tracker.lines)
            assert old_line.status is LineStatus.DELAYED
            assert not client.is_closed

    asyncio.run(scenario())


def test_synthetic_unknown_marker_preserves_raw_details() -> None:
    text = (_FIXTURES / "nankai_20261004112434.html").read_text(encoding="utf-8")
    text = text.replace('class="triangle"', 'class="new-marker"', 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=text),
        )) as client:
            provider = NankaiProvider(client=client)
            await provider.refresh()
            assert provider.koya.status is LineStatus.UNKNOWN
            assert provider.koya.source_status is not None
            assert "new-marker" in provider.koya.source_status
            assert "列車が遅れています。" in provider.koya.alerts[0].description
            assert provider.koya.alerts[0].effect is AlertEffect.UNKNOWN
            assert provider.semboku.status is LineStatus.DELAYED

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "missing_group", "duplicate_group", "missing_route", "unknown_route",
    "missing_marker", "conflicting_normal", "missing_details", "unknown_heading",
    "invalid_time", "missing_time", "special_train_conflicting_normal",
])
def test_synthetic_broken_html_keeps_complete_previous_snapshot(fault: str) -> None:
    soup = BeautifulSoup((_FIXTURES / "nankai_normal.html").read_text(encoding="utf-8"), "html.parser")
    if fault in ("missing_group", "duplicate_group"):
        node = soup.select_one("#semboku-line-wrap")
        assert node is not None
        if fault == "missing_group":
            node.decompose()
        else:
            soup.append(BeautifulSoup(str(node), "html.parser"))
    elif fault in ("missing_route", "unknown_route", "missing_marker", "conflicting_normal"):
        node = soup.select_one("#nankai-line > ul > li")
        assert node is not None
        if fault == "missing_route":
            node.decompose()
        elif fault == "unknown_route":
            node.append("新しい路線")
        else:
            marker = node.select_one("span")
            assert marker is not None
            if fault == "missing_marker":
                marker.decompose()
            else:
                marker["class"] = "times"
    elif fault == "special_train_conflicting_normal":
        node = soup.select_one("#nankai-line > ul > li:last-child > span")
        assert node is not None
        node["class"] = "triangle"
    elif fault in ("missing_details", "unknown_heading"):
        soup = BeautifulSoup((_FIXTURES / "nankai_20261004112434.html").read_text(encoding="utf-8"), "html.parser")
        node = soup.select_one("#koya-line-wrap > .alert" if fault == "missing_details" else "#koya-line-wrap .col-10.col-md-2")
        assert node is not None
        if fault == "missing_details":
            node.decompose()
        else:
            node.string = "未登録線"
    else:
        node = soup.select_one(".rosenzu-update-time > span")
        assert node is not None
        if fault == "missing_time":
            node.decompose()
        else:
            node.string = "更新時刻 : 2026/13/01 20:00"
    broken = False

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)) if broken else
            httpx.Response(200, content=(_FIXTURES / "nankai_20261004112434.html").read_bytes()),
        )) as client:
            provider = NankaiProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert len(provider.delay_lines) == 2

    asyncio.run(scenario())


def test_network_failure_is_reported_without_losing_snapshot() -> None:
    broken = False

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(503) if broken else
            httpx.Response(200, content=(_FIXTURES / "nankai_normal.html").read_bytes()),
        )) as client:
            tracker = Tracker(enabled_providers=("nankai",), client=client)
            await tracker.refresh()
            previous = tracker.nankai.lines
            broken = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert isinstance(captured.value.errors[ProviderId("nankai")], FetchError)
            assert tracker.nankai.lines is previous

    asyncio.run(scenario())
