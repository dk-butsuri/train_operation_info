"""Official normal fixtures and synthetic cases based on the published legend."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import LINE_CATALOG, AlertEffect, LineId, LineStatus, OperatorId, ProviderId, UsagePermission
from train_operation_info.providers.taipei_metro import TaipeiMetroProvider
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"


def _normal() -> str:
    return (_FIXTURES / "taipei_metro_normal.html").read_text(encoding="utf-8")


def _element(soup: BeautifulSoup | Tag, selector: str) -> Tag:
    element = soup.select_one(selector)
    assert element is not None
    return element


def _synthetic_light(marker: str, label: str, *, code: str = "BL") -> str:
    soup = BeautifulSoup(_normal(), "html.parser")
    card = next(
        item for item in soup.select(".realstatusdetail__item")
        if _element(item, ".linecode").get_text(strip=True) == code
    )
    name = _element(card, ".linetitletw").get_text(strip=True)
    image = _element(card, ".realstatus__img img")
    image["src"] = f"/2026/images/realstatus/{marker}"
    image["alt"] = image["title"] = name + label
    _element(soup, ".realstatus__text").string = "合成テスト：運行情報の本文。文湖線は正常です。"
    return str(soup)


@pytest.mark.parametrize(
    ("fixture", "expected_update"),
    [
        ("taipei_metro_normal.html", "2026-11-01T23:02:03+08:00"),
        ("taipei_metro_20261024103101.html", "2026-10-24T18:31:02+08:00"),
    ],
)
def test_official_normal_fixtures(fixture: str, expected_update: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://tpweb.metro.taipei/2026/"
        return httpx.Response(200, content=(_FIXTURES / fixture).read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("taipei_metro",), client=client)
            provider = tracker.taipei_metro
            initial_unknown = tracker.unknown_lines
            assert len(initial_unknown) == 6
            await tracker.refresh()
            expected_ids = {
                LineId("tw:trtc:wenhu"), LineId("tw:trtc:tamsui_xinyi"),
                LineId("tw:trtc:songshan_xindian"), LineId("tw:trtc:zhonghe_xinlu"),
                LineId("tw:trtc:bannan"), LineId("tw:ntmetro:circular"),
            }
            assert {line.line_id for line in tracker.lines} == expected_ids
            assert provider.lines == (
                provider.wenhu, provider.tamsui_xinyi, provider.songshan_xindian,
                provider.zhonghe_xinlu, provider.bannan, provider.circular,
            )
            for line in provider.lines:
                assert line.status is LineStatus.NORMAL
                assert line.updated_at == datetime.fromisoformat(expected_update)
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.provider_id == ProviderId("taipei_metro")
            assert provider.bannan.operator.operator_id == OperatorId("tw:trtc")
            assert provider.circular.operator.operator_id == OperatorId("tw:ntmetro")
            assert not tracker.alerts and not tracker.affected_lines and not tracker.unknown_lines
            assert all(unfetched.status is LineStatus.UNKNOWN for unfetched in tracker.singapore_mrt.lines)
            assert not client.is_closed
            assert provider.metadata.usage_permission is UsagePermission.COMMERCIAL_ALLOWED

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("marker", "label", "expected", "effect"),
    [
        ("lightyellow.gif", "路線運行延誤", LineStatus.DELAYED, AlertEffect.DELAYS),
        ("lightred.gif", "路線局部受阻", LineStatus.PARTIAL_SUSPENSION, AlertEffect.REDUCED_SERVICE),
        ("unknown.gif", "未確認の表示", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
        ("lightgreen.png", "未確認の表示", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
    ],
)
def test_synthetic_lights_preserve_scope_and_details(
    marker: str, label: str, expected: LineStatus, effect: AlertEffect,
) -> None:
    html = _synthetic_light(marker, label)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=html),
        )) as client:
            provider = TaipeiMetroProvider(client=client)
            await provider.refresh()
            assert provider.bannan.status is expected
            assert all(line.status is LineStatus.NORMAL for line in provider.lines if line is not provider.bannan)
            alert, = provider.alerts
            assert alert.affected_line_ids == (LineId("tw:trtc:bannan"),)
            assert alert.effect is effect
            assert label in alert.title
            assert "合成テスト" in alert.description
            assert alert.language == "zh-Hant"
            assert alert.active_from is None and alert.active_until is None

    asyncio.run(scenario())


def test_synthetic_closed_hours_are_not_a_disruption() -> None:
    soup = BeautifulSoup(_normal(), "html.parser")
    for item in soup.select(".realstatusdetail__item"):
        image = _element(item, ".realstatus__img img")
        image["src"] = "/2026/images/realstatus/lightgray.png"
        image["alt"] = _element(item, ".linetitletw").get_text(strip=True) + "非營運時間"
    _element(soup, ".realstatus__text").string = "非營運時間"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = TaipeiMetroProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert all("非營運時間" in (line.source_status or "") for line in provider.lines)
            assert not provider.alerts

    asyncio.run(scenario())


def test_synthetic_recovery_replaces_old_alerts_and_preserves_old_snapshots() -> None:
    payload = _synthetic_light("lightyellow.gif", "路線運行延誤")

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=payload),
        )) as client:
            provider = TaipeiMetroProvider(client=client)
            await provider.refresh()
            previous = provider.bannan
            payload = _synthetic_light("lightred.gif", "路線局部受阻")
            await provider.refresh()
            partial = provider.bannan
            assert partial.status is LineStatus.PARTIAL_SUSPENSION
            payload = _normal()
            await provider.refresh()
            recovered = provider.bannan
            assert not provider.alerts and recovered.status is LineStatus.NORMAL
            assert previous.status is LineStatus.DELAYED and previous.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", [
    "panel", "route", "duplicate", "code", "name", "image", "alt", "timestamp", "time_value", "message",
])
def test_synthetic_malformed_page_preserves_last_disruption(damage: str) -> None:
    soup = BeautifulSoup(_normal(), "html.parser")
    if damage == "duplicate":
        _element(soup, ".linecode").string = "BL"
    elif damage == "code":
        _element(soup, ".linecode").string = "NEW"
    elif damage == "name":
        _element(soup, ".linetitletw").string = "別の路線"
    elif damage == "alt":
        del _element(soup, ".realstatusdetail__item img")["alt"]
    elif damage == "time_value":
        _element(soup, "#LabelUpdatetime").string = "資料更新時間：invalid"
    else:
        selector = {
            "panel": "#UpdatePanelRealStatusDetail", "route": ".realstatusdetail__item",
            "image": ".realstatusdetail__item img", "timestamp": "#LabelUpdatetime",
            "message": ".realstatus__text",
        }[damage]
        _element(soup, selector).decompose()
    payload = _synthetic_light("lightyellow.gif", "路線運行延誤")

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=payload),
        )) as client:
            provider = TaipeiMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            payload = str(soup)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.bannan.status is LineStatus.DELAYED

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_fetch_failure_keeps_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and failure == "connection":
            raise httpx.ConnectError("synthetic connection failure", request=request)
        return httpx.Response(503) if broken else httpx.Response(200, text=_normal())

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TaipeiMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_unscoped_notice_keeps_message_links_and_empty_scope() -> None:
    soup = BeautifulSoup(_normal(), "html.parser")
    _element(soup, ".realstatus__text").string = "合成テスト：影響路線未指定"
    image = soup.new_tag("img", src="/2026/images/synthetic-map.png")
    _element(soup, ".abnormalpic").append(image)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = TaipeiMetroProvider(client=client)
            tracker = Tracker(enabled_providers=("taipei_metro",), overrides=(provider,))
            assert tracker.providers == (provider,)
            await tracker.refresh()
            assert len(tracker.unknown_lines) == 6
            alert, = tracker.alerts
            assert alert.affected_line_ids == ()
            assert "影響路線未指定" in alert.description
            assert "https://tpweb.metro.taipei/2026/images/synthetic-map.png" in alert.description

    asyncio.run(scenario())
