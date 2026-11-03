"""Archived official states; malformed and unknown scenarios are synthetic."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, LineId, LineScope, LineStatus,
    OperatorId, UsagePermission,
)
from train_operation_info.providers.tra import TraProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.railway.gov.tw/tra-tip-web/tip/tip007/tip711/blockList"


def _html(name: str = "tra_normal.html") -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _element(soup: BeautifulSoup | Tag, selector: str) -> Tag:
    element = soup.select_one(selector)
    assert element is not None
    return element


@pytest.mark.parametrize(("fixture", "delayed", "notices", "alerts", "update"), [
    ("tra_normal.html", 0, 0, 0, "2026-11-02T23:56:00+08:00"),
    ("tra_20260702152705.html", 0, 0, 0, "2026-07-02T23:27:00+08:00"),
    ("tra_20240213061449.html", 0, 1, 2, "2024-02-13T14:14:00+08:00"),
    ("tra_20240403013943.html", 0, 2, 2, "2024-04-03T09:39:00+08:00"),
    ("tra_20240804153201.html", 1, 2, 3, "2024-08-04T23:32:00+08:00"),
    ("tra_20241004110527.html", 0, 3, 4, "2024-10-04T19:05:00+08:00"),
    ("tra_20241117082659.html", 0, 3, 3, "2024-11-17T16:26:00+08:00"),
    ("tra_20250310054809.html", 1, 1, 2, "2025-03-10T13:48:00+08:00"),
    ("tra_20250707021531.html", 0, 7, 12, "2025-07-07T10:15:00+08:00"),
    ("tra_20250813015801.html", 0, 5, 5, "2025-08-13T09:58:00+08:00"),
])
def test_official_fixtures(
    fixture: str, delayed: int, notices: int, alerts: int, update: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == _URL
        return httpx.Response(200, text=_html(fixture))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("tra",), client=client)
            provider = tracker.tra
            assert len(provider.unknown_lines) == 12
            await tracker.refresh()
            assert len(provider.lines) == 12
            assert provider.lines == (
                provider.western, provider.western_coast, provider.eastern,
                provider.south_link, provider.chengzhui, provider.pingxi,
                provider.shenao, provider.liujia, provider.neiwan, provider.jiji,
                provider.shalun, provider.suaoxin_suao,
            )
            assert len(provider.delay_lines) == delayed
            assert sum(line.status is LineStatus.ALERT for line in provider.lines) == notices
            assert len(provider.alerts) == alerts
            assert not provider.unknown_lines
            assert tracker.alerts == provider.alerts
            for line in provider.lines:
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.operator.operator_id == OperatorId("tw:tra")
                assert line.provider_id == "tra"
                assert line.updated_at == datetime.fromisoformat(update)
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            for alert in provider.alerts:
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None
                assert alert.language == "zh-Hant"
                assert len(alert.affected_line_ids) == 1
                assert alert.source_url == _URL
            assert provider.western.scope is LineScope.GROUP
            assert provider.eastern.scope is LineScope.GROUP
            assert provider.south_link.scope is LineScope.GROUP
            assert provider.pingxi.scope is LineScope.LINE
            assert provider.metadata.usage_permission is UsagePermission.COMMERCIAL_ALLOWED
            assert not client.is_closed
            assert all(line.status is LineStatus.UNKNOWN for line in tracker.thsr.lines)

    asyncio.run(scenario())


def test_archived_delay_recovery_and_all_clear_preserve_original_snapshots() -> None:
    payload = _html("tra_20250310054809.html")

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=payload))) as client:
            provider = TraProvider(client=client)
            await provider.refresh()
            delayed = provider.eastern
            alert, = delayed.alerts
            assert delayed.status is LineStatus.DELAYED and alert.effect is AlertEffect.DELAYS
            assert "雙溪-三貂嶺" in alert.title and "東正線單線雙向行車" in alert.description
            assert "預計恢復時間:評估中" in alert.description
            assert alert.affected_line_ids == (LineId("tw:tra:eastern_group"),)
            payload = _html("tra_20240213061449.html")
            await provider.refresh()
            recovered = provider.pingxi
            assert recovered.status is LineStatus.NORMAL
            recovery, = recovered.alerts
            assert recovery.effect is AlertEffect.OTHER and "恢復正常 (Resume)" in recovery.title
            assert provider.jiji.status is LineStatus.ALERT
            # Different incident captures: this is snapshot replacement, not a
            # claim that the 2024 recovery resolves the 2025 delay.
            payload = _html("tra_20260702152705.html")
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert not provider.alerts
            assert delayed.status is LineStatus.DELAYED and delayed.alerts
            assert recovered.alerts

    asyncio.run(scenario())


def test_typhoon_rows_and_long_term_construction_remain_separate_notices() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=_html("tra_20250707021531.html")),
        )) as client:
            provider = TraProvider(client=client)
            await provider.refresh()
            assert len(provider.western.alerts) == 4
            assert len(provider.jiji.alerts) == 2
            assert "隧道及邊坡改善工程" in provider.jiji.alerts[0].description
            assert "預計2025/12/31 23:59恢復" in provider.jiji.alerts[0].description
            assert "今(7)日集集線停駛" in provider.jiji.alerts[0].description
            assert all(alert.effect is AlertEffect.OTHER for alert in provider.alerts)
            assert not provider.active_alerts
            assert len(provider.unclassified_alerts) == 12

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["color", "legend", "summary", "summary_color", "normal_with_rows", "marker"])
def test_synthetic_unknown_or_contradictory_states_are_not_normal(mutation: str) -> None:
    soup = BeautifulSoup(_html("tra_20250310054809.html"), "html.parser")
    row_marker = _element(soup, "table span")
    summary = next(dl for dl in soup.select(".now_status") if _element(dl, "dt").get_text() == "東部幹線")
    if mutation == "color":
        row_marker["style"] = "color: #123456"
    elif mutation == "legend":
        _element(soup, ".info label:nth-of-type(2)").string = "合成テスト：新しい意味"
    elif mutation == "summary":
        _element(summary, "label").string = "合成テスト：未確認の状態"
    elif mutation == "summary_color":
        _element(summary, "dd")["style"] = "color: #123456"
    elif mutation == "marker":
        row_marker["class"] = "icon-fa new-marker"
    else:
        _element(summary, "label").string = "全線正常運行"
        _element(summary, "dd")["class"] = "icon-fa circle-o"
        _element(summary, "dd")["style"] = "color: #5bb900"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=str(soup)))) as client:
            provider = TraProvider(client=client)
            await provider.refresh()
            assert provider.eastern.status is LineStatus.UNKNOWN
            assert "東正線單線雙向行車" in provider.eastern.alerts[0].description
            assert provider.eastern.alerts[0].affected_line_ids == (LineId("tw:tra:eastern_group"),)
            assert provider.jiji.status is LineStatus.ALERT
            assert provider.western.status is LineStatus.NORMAL

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", [
    "content", "panel", "route", "duplicate", "unknown_route", "table", "cell",
    "empty", "section", "color", "time", "time_value", "legend", "empty_rows",
])
def test_synthetic_malformed_responses_keep_previous_snapshot(damage: str) -> None:
    soup = BeautifulSoup(_html("tra_20250310054809.html"), "html.parser")
    if damage in ("duplicate", "unknown_route"):
        _element(soup, ".now_status dt").string = "集集線" if damage == "duplicate" else "未知線"
    elif damage == "color":
        del _element(soup, "table span")["style"]
    elif damage == "empty":
        _element(soup, "table td").clear()
    elif damage == "time_value":
        _element(soup, "#content > p:nth-of-type(2)").string = "更新時間：invalid"
    elif damage == "empty_rows":
        _element(soup, "table tr").decompose()
    else:
        selector = {
            "content": "#content", "panel": ".operation-list", "route": ".now_status",
            "table": "table", "cell": "table td", "section": "table label",
            "time": "#content > p:nth-of-type(2)", "legend": ".info",
        }[damage]
        _element(soup, selector).decompose()
    payload = _html("tra_20250310054809.html")

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=payload))) as client:
            provider = TraProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            payload = str(soup)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous and provider.eastern.status is LineStatus.DELAYED

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_fetch_failure_retains_previous_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            if failure == "connection":
                raise httpx.ConnectError("synthetic failure", request=request)
            return httpx.Response(503)
        return httpx.Response(200, text=_html("tra_20250310054809.html"))

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TraProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_tracker_selection_and_injection_do_not_enable_other_sources() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url) == _URL
        return httpx.Response(200, text=_html())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TraProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not calls and disabled.tra is provider
            selected = Tracker(enabled_providers=("tra",), overrides=(provider,))
            assert selected.providers == (provider,)
            await selected.refresh()
            assert calls == [_URL]
            assert selected.lines == provider.lines
            assert "tra" in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())
