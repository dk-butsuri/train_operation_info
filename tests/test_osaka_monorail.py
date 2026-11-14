"""Captured abnormal map; all topology mutations and recovery below are synthetic."""

import asyncio
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineStatus
from train_operation_info.providers.osaka_monorail import OsakaMonorailProvider

_FIXTURES = Path(__file__).parent / "fixtures"


def _captured() -> str:
    return (_FIXTURES / "osaka_monorail_partial_20261114.html").read_text(encoding="utf-8")


def test_captured_partial_suspension_and_saito_delay() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=_captured()),
        )) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.PARTIAL_SUSPENSION
            assert provider.saito.status is LineStatus.DELAYED
            assert provider.main.line_id == LineId("jp:osaka_monorail:main")
            assert provider.saito.line_id == LineId("jp:osaka_monorail:saito")
            assert provider.main.alerts[0].effect is AlertEffect.REDUCED_SERVICE
            assert provider.saito.alerts[0].effect is AlertEffect.DELAYS
            assert len(provider.active_alerts) == 2
            for line in provider.lines:
                alert, = line.alerts
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.timing is AlertTiming.ACTIVE
                assert alert.active_from is None and alert.active_until is None
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
                assert 'Service has' not in alert.description
                assert 'dispTime' not in alert.description
            # Preserve all segment states, including delays alongside partial suspension.
            assert provider.main.source_status is not None
            assert provider.main.source_status.count(': stop') == 7
            assert provider.main.source_status.count(': delay') == 6
            assert provider.saito.source_status is not None
            assert provider.saito.source_status.count(': delay') == 4

    asyncio.run(scenario())


@pytest.mark.parametrize(("marker", "main", "saito"), [
    ("stop", LineStatus.SUSPENDED, LineStatus.SUSPENDED),
    ("delay", LineStatus.DELAYED, LineStatus.DELAYED),
    ("normal", LineStatus.NORMAL, LineStatus.NORMAL),
    ("future", LineStatus.UNKNOWN, LineStatus.UNKNOWN),
    ("", LineStatus.UNKNOWN, LineStatus.UNKNOWN),
    ("normal stop", LineStatus.UNKNOWN, LineStatus.UNKNOWN),
])
def test_synthetic_map_classes(marker: str, main: LineStatus, saito: LineStatus) -> None:
    soup = BeautifulSoup(_captured(), "html.parser")
    for segment in soup.select("span[id^=line]"):
        segment["class"] = marker
    # The narrative stays unchanged: only the dedicated segment states classify service.
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            assert provider.main.status is main
            assert provider.saito.status is saito
            if main is LineStatus.UNKNOWN:
                assert not provider.active_alerts
                assert len(provider.unclassified_alerts) == 2

    asyncio.run(scenario())


def test_synthetic_unknown_segment_does_not_establish_complete_route_status() -> None:
    html = _captured().replace('class="stop" id="line17-18"', 'class="future" id="line17-18"')
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.saito.status is LineStatus.DELAYED
    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["segment", "duplicate", "route", "station", "wrong_id", "parent", "map", "missing_map", "http"])
def test_synthetic_broken_map_or_http_failure_retains_abnormal_snapshot(damage: str) -> None:
    original = _captured()
    soup = BeautifulSoup(original, "html.parser")
    segment = soup.select_one("#line17-18")
    assert segment is not None
    if damage == "segment":
        segment.decompose()
    elif damage == "duplicate":
        segment.insert_after(BeautifulSoup(str(segment), "html.parser"))
    elif damage == "route":
        rail = soup.select_one(".stationMap__topRail")
        assert rail is not None
        rail.decompose()
    elif damage == "station":
        name = soup.select_one("#station_18 .-station")
        assert name is not None
        name.decompose()
    elif damage == "wrong_id":
        segment["id"] = "line17-99"
    elif damage == "parent":
        parent = soup.select_one("#station_18")
        assert parent is not None
        parent["id"] = "station_99"
    elif damage == "map":
        station_map = soup.select_one(".stationMap__wrap")
        assert station_map is not None
        station_map.insert_after(BeautifulSoup(str(station_map), "html.parser"))
    elif damage == "missing_map":
        station_map = soup.select_one(".stationMap__wrap")
        assert station_map is not None
        station_map.decompose()
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503 if broken and damage == "http" else 200,
                              text=str(soup) if broken else original)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError if damage == "http" else ParseError):
                await provider.refresh()
            assert provider.lines is previous
    asyncio.run(scenario())


def test_synthetic_refresh_to_captured_normal_clears_both_alerts() -> None:
    recovered = False
    normal = (_FIXTURES / "monorail_normal.html").read_text(encoding="utf-8")

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=normal if recovered else _captured()),
        )) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            assert len(provider.active_alerts) == 2
            recovered = True
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert not provider.alerts
    asyncio.run(scenario())


def test_synthetic_abnormal_summary_without_map_keeps_unscoped_notice() -> None:
    soup = BeautifulSoup(_captured(), "html.parser")
    detail = soup.select_one(".operationStatus__detail")
    assert detail is not None
    detail.decompose()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = OsakaMonorailProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            alert, = provider.alerts
            assert alert.affected_line_ids == ()
            assert alert.timing is AlertTiming.UNKNOWN
    asyncio.run(scenario())
