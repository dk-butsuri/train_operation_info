"""Real normal/suspension/reduced-speed captures; synthetic unknown/damage cases."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, LINE_CATALOG, LineId, LineScope, LineStatus, ProviderId,
)
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.taoyuan_metro import TaoyuanMetroProvider
from train_operation_info.providers.taoyuan_metro.provider import _parse

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.tymetro.com.tw/tymetro-new/tw/"
_NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _synthetic(marker: str = "green", label: str = "正常營運") -> str:
    # Synthesised structure based on the two responsive source panels.
    panel = f'<div class="operation"><p>最新營運狀態<span class="{marker}">{label}</span></p></div>'
    return f'<div class="banner">{panel}{panel}</div>'


@pytest.mark.parametrize(("name", "status", "label"), [
    ("normal_20261104", LineStatus.NORMAL, "正常營運"),
    ("normal_20240408100245", LineStatus.NORMAL, "正常營運"),
    ("suspended_20240403012130", LineStatus.SUSPENDED, "全線停駛"),
    ("slow_20260711043649", LineStatus.ALERT, "減速營運"),
])
def test_real_official_operating_panels(name: str, status: LineStatus, label: str) -> None:
    body = (_FIXTURES / f"taoyuan_metro_{name}.html").read_bytes()

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _URL
            assert request.headers["user-agent"] == USER_AGENT
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaoyuanMetroProvider(client=client)
            await provider.refresh()
            line = provider.airport
            assert line.status is status and line.source_status == label
            assert line.line_id == LineId("tw:tymetro:airport")
            assert line.operator.name == "桃園大眾捷運股份有限公司"
            assert line.operator is LINE_CATALOG[line.line_id].operator
            assert line.scope is LineScope.LINE
            assert line.updated_at is None
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timezone.utc.utcoffset(None)
            assert len(line.alerts) == (0 if status is LineStatus.NORMAL else 1)
            for alert in line.alerts:
                assert alert.description == label
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.language == "zh-Hant"
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is alert.active_until is None
                assert alert.effect is (AlertEffect.NO_SERVICE if status is LineStatus.SUSPENDED else AlertEffect.OTHER)
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("marker", "label"), [
    ("green", "未知狀態"), ("blue", "正常營運"), ("green", "全線停駛"),
    ("red", "正常營運"), ("yellow", "全線停駛"), ("green extra", "正常營運"),
    ("red", "明日全線停駛"), ("green", "正常營運，但另有公告"),
])
def test_synthetic_unknown_or_contradictory_pair_keeps_original(marker: str, label: str) -> None:
    line, = _parse(_synthetic(marker, label), TaoyuanMetroProvider().airport, _NOW)
    assert line.status is LineStatus.UNKNOWN
    assert line.source_status == f"{label} [{' '.join(sorted(marker.split()))}]"
    assert label in line.alerts[0].description
    assert line.alerts[0].effect is AlertEffect.UNKNOWN
    assert line.alerts[0].timing is AlertTiming.UNKNOWN


def test_synthetic_news_and_page_clock_do_not_change_panel_status() -> None:
    html = _synthetic() + (
        '<div id="timereload">20:30</div><div class="news">明日全線停駛</div>'
    )
    line, = _parse(html, TaoyuanMetroProvider().airport, _NOW)
    assert line.status is LineStatus.NORMAL
    assert line.alerts == () and line.updated_at is None


@pytest.mark.parametrize("damage", [
    "missing_panels", "one_panel", "extra_panel", "heading", "missing_status",
    "duplicate_status", "empty_status", "missing_marker", "disagreement", "empty_marker",
])
def test_synthetic_damage_preserves_previous_snapshot(damage: str) -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_synthetic(), "html.parser")
    panels = soup.select(".operation")
    status = soup.select_one("span")
    assert status is not None
    if damage == "missing_panels":
        html = "maintenance"
    elif damage == "heading":
        html = str(soup).replace("最新營運狀態", "其他狀態")
    else:
        if damage == "one_panel":
            panels[0].decompose()
        elif damage == "extra_panel":
            panels[0].insert_after(BeautifulSoup(str(panels[0]), "html.parser"))
        elif damage == "missing_status":
            status.decompose()
        elif damage == "duplicate_status":
            status.insert_after(BeautifulSoup(str(status), "html.parser"))
        elif damage == "empty_status":
            status.string = " "
        elif damage == "missing_marker":
            del status["class"]
        elif damage == "empty_marker":
            status["class"] = ""
        elif damage == "disagreement":
            status["class"] = "red"
            status.string = "全線停駛"
        html = str(soup)

    async def scenario() -> None:
        broken = False

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html if broken else _synthetic("red", "全線停駛"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaoyuanMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.airport.status is LineStatus.SUSPENDED

    asyncio.run(scenario())


def test_archived_normal_after_suspension_clears_old_alert() -> None:
    async def scenario() -> None:
        recovered = False

        def handler(request: httpx.Request) -> httpx.Response:
            name = "normal_20240408100245" if recovered else "suspended_20240403012130"
            return httpx.Response(200, content=(_FIXTURES / f"taoyuan_metro_{name}.html").read_bytes())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaoyuanMetroProvider(client=client)
            await provider.refresh()
            old = provider.airport
            assert old.status is LineStatus.SUSPENDED and old.alerts
            recovered = True
            await provider.refresh()
            assert provider.airport.status is LineStatus.NORMAL
            assert provider.alerts == ()
            assert old.status is LineStatus.SUSPENDED and old.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "transport", "encoding"])
def test_synthetic_fetch_failure_is_atomic(failure: str) -> None:
    async def scenario() -> None:
        broken = False

        def handler(request: httpx.Request) -> httpx.Response:
            if broken:
                if failure == "transport":
                    raise httpx.ConnectError("offline", request=request)
                if failure == "encoding":
                    return httpx.Response(200, content=b"\xff")
                return httpx.Response(503)
            return httpx.Response(200, text=_synthetic())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaoyuanMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError if failure == "encoding" else FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_tracker_selection_override_and_independent_failure() -> None:
    async def scenario() -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, text=_synthetic()) if str(request.url) == _URL else httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaoyuanMetroProvider(client=client)
            assert ProviderId("taoyuan_metro") in {p.provider_id for p in Tracker().providers}
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert disabled.taoyuan_metro is provider and requested == []
            tracker = Tracker(enabled_providers=("taoyuan_metro",), overrides=(provider,))
            await tracker.refresh()
            assert tracker.providers == (provider,) and tracker.lines == provider.lines
            assert requested == [_URL]
            tracker = Tracker(enabled_providers=("taoyuan_metro", "jrw"), client=client)
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("jrw")}
            assert tracker.taoyuan_metro.airport.status is LineStatus.NORMAL
            assert tracker.jrw.osaka_loop.status is LineStatus.UNKNOWN

    asyncio.run(scenario())
