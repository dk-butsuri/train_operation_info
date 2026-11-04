"""Real normal panels; explicitly synthetic unknown/damage/recovery scenarios."""

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
from train_operation_info.providers.kaohsiung_metro import KaohsiungMetroProvider
from train_operation_info.providers.kaohsiung_metro.provider import _parse

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.krtc.com.tw/"
_NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _synthetic(metro: str = "捷運全線正常營運", marker: str = "g", rail: str = "輕軌全線正常營運") -> str:
    rows = f'<div><div class="{marker} ci"></div> {metro} </div><div><div class="g ci"></div> {rail} </div>'
    return f'<div id="RtStatus">{rows}</div><div id="RtStatusMobile">{rows}</div>'


@pytest.mark.parametrize("fixture", ["normal_20261104", "normal_20261017100942"])
def test_real_normal_panels(fixture: str) -> None:
    body = (_FIXTURES / f"kaohsiung_metro_{fixture}.html").read_bytes()

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _URL
            assert request.headers["user-agent"] == USER_AGENT
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KaohsiungMetroProvider(client=client)
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            await provider.refresh()
            assert provider.metro.scope is LineScope.GROUP
            assert provider.light_rail.scope is LineScope.LINE
            assert provider.metro.line_id == LineId("tw:krtc:metro")
            assert provider.light_rail.line_id == LineId("tw:krtc:light_rail")
            assert provider.metro.source_status == "捷運全線正常營運"
            assert provider.light_rail.source_status == "輕軌全線正常營運"
            assert len(provider.lines) == 2 and provider.alerts == ()
            for line in provider.lines:
                assert line.status is LineStatus.NORMAL
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.operator.name == "高雄捷運股份有限公司"
                assert line.updated_at is None
                assert line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timezone.utc.utcoffset(None)

    asyncio.run(scenario())


@pytest.mark.parametrize(("marker", "label"), [
    ("r", "捷運全線停駛"),
    ("y", "捷運部分路段受阻"),
    ("g", "捷運明日停駛，今日正常營運"),
    ("g", "捷運未停駛"),
    ("g", "捷運恢復正常營運"),
    ("g", "捷運全線正常營運（附加未確認公告）"),
    ("new", "捷運全線正常營運"),
    ("r", "捷運全線正常營運"),
])
def test_synthetic_unverified_states_never_infer_impact_or_timing(marker: str, label: str) -> None:
    lines = _parse(_synthetic(label, marker), KaohsiungMetroProvider().lines, _NOW)
    metro, light_rail = lines
    assert metro.status is LineStatus.UNKNOWN
    assert light_rail.status is LineStatus.NORMAL
    assert metro.source_status is not None
    assert label in metro.source_status and marker in metro.source_status
    alert, = metro.alerts
    assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
    assert alert.affected_line_ids == ()
    assert alert.active_from is None and alert.active_until is None
    assert alert.language == "zh-Hant" and label in alert.description


def test_light_rail_unknown_does_not_change_mrt_and_links_are_retained() -> None:
    html = _synthetic(rail='輕軌狀態確認中 <a href="/Information/notice?id=test">詳細</a>')
    metro, rail = _parse(html, KaohsiungMetroProvider().lines, _NOW)
    assert metro.status is LineStatus.NORMAL and rail.status is LineStatus.UNKNOWN
    assert "https://www.krtc.com.tw/Information/notice?id=test" in rail.alerts[0].description
    # Even a normal label with an additional reference is not silently discarded.
    html = _synthetic(metro='捷運全線正常營運<a href="/Information/notice"></a>')
    assert _parse(html, KaohsiungMetroProvider().lines, _NOW)[0].status is LineStatus.UNKNOWN


def test_rows_are_identified_by_group_heading_rather_than_position() -> None:
    html = _synthetic().replace(
        '<div><div class="g ci"></div> 捷運全線正常營運 </div><div><div class="g ci"></div> 輕軌全線正常營運 </div>',
        '<div><div class="g ci"></div> 輕軌全線正常營運 </div><div><div class="g ci"></div> 捷運全線正常營運 </div>',
    )
    assert all(line.status is LineStatus.NORMAL for line in _parse(html, KaohsiungMetroProvider().lines, _NOW))


@pytest.mark.parametrize("html", [
    "<html></html>",
    _synthetic().replace('id="RtStatusMobile"', 'id="Other"'),
    _synthetic() + _synthetic(),
    _synthetic().replace('捷運全線正常營運', ''),
    _synthetic().replace('捷運全線正常營運', '捷運'),
    _synthetic().replace('捷運全線正常營運', '輕軌全線正常營運'),
    _synthetic().replace('捷運全線正常營運', '別事業者の情報'),
    _synthetic().replace('<div class="g ci"></div>', ''),
    _synthetic().replace('<div class="g ci"></div>', '<div class="g ci"></div><div class="g ci"></div>'),
    _synthetic().replace('<div class="g ci"></div>', '<div class="g ci">未確認文字</div>'),
    _synthetic().replace('捷運全線正常營運', '捷運全線正常營運<a href=""></a>'),
    _synthetic().replace('捷運全線正常營運', '捷運未確認', 1),
    _synthetic().replace('</div></div><div id="RtStatusMobile">', '</div><div>追加</div></div><div id="RtStatusMobile">'),
])
def test_synthetic_damage_keeps_both_previous_lines(html: str) -> None:
    async def scenario() -> None:
        broken = False

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html if broken else _synthetic())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KaohsiungMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "transport", "encoding"])
def test_synthetic_fetch_failure_is_atomic(failure: str) -> None:
    async def scenario() -> None:
        broken = False

        def handler(request: httpx.Request) -> httpx.Response:
            if broken:
                if failure == "transport":
                    raise httpx.ConnectError("offline", request=request)
                return httpx.Response(200, content=b"\xff") if failure == "encoding" else httpx.Response(503)
            return httpx.Response(200, text=_synthetic())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KaohsiungMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError if failure == "encoding" else FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_unknown_to_normal_clears_alerts_and_keeps_old_value_immutable() -> None:
    async def scenario() -> None:
        recovered = False
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=_synthetic() if recovered else _synthetic("捷運確認中", "y")),
        )) as client:
            provider = KaohsiungMetroProvider(client=client)
            await provider.refresh()
            previous = provider.metro
            assert previous.status is LineStatus.UNKNOWN and previous.alerts
            recovered = True
            await provider.refresh()
            assert provider.metro.status is LineStatus.NORMAL and provider.alerts == ()
            assert previous.status is LineStatus.UNKNOWN and previous.alerts

    asyncio.run(scenario())


def test_tracker_selection_override_and_independent_failure() -> None:
    async def scenario() -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, text=_synthetic()) if str(request.url) == _URL else httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KaohsiungMetroProvider(client=client)
            assert ProviderId("kaohsiung_metro") in {p.provider_id for p in Tracker().providers}
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert disabled.kaohsiung_metro is provider and not requested
            selected = Tracker(enabled_providers=("kaohsiung_metro",), overrides=(provider,))
            await selected.refresh()
            assert selected.providers == (provider,) and selected.lines == provider.lines
            assert requested == [_URL]
            tracker = Tracker(enabled_providers=("kaohsiung_metro", "jrw"), client=client)
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("jrw")}
            assert tracker.kaohsiung_metro.metro.status is LineStatus.NORMAL
            assert tracker.jrw.osaka_loop.status is LineStatus.UNKNOWN

    asyncio.run(scenario())
