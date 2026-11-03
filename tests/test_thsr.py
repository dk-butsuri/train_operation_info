"""Official THSR HTML excerpts and explicitly synthetic failure/recovery cases."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, AlertEffect, LineId, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.thsr import ThsrProvider
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123"


def _html(name: str = "thsr_normal.html") -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(("fixture", "status", "updated"), [
    ("thsr_normal.html", LineStatus.NORMAL, None),
    ("thsr_20260830041403.html", LineStatus.NORMAL, None),
    ("thsr_20240403005339.html", LineStatus.DELAYED, "2024-04-03T08:33:00+08:00"),
    ("thsr_20250227055330.html", LineStatus.DELAYED, "2025-02-27T13:49:00+08:00"),
    ("thsr_20241003073858.html", LineStatus.ALERT, "2024-10-03T10:42:00+08:00"),
    ("thsr_20260711043641.html", LineStatus.ALERT, "2026-07-11T00:13:00+08:00"),
])
def test_official_status(fixture: str, status: LineStatus, updated: str | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == _URL
        return httpx.Response(200, text=_html(fixture))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ThsrProvider(client=client)
            assert provider.main.status is LineStatus.UNKNOWN
            await provider.refresh()
            line = provider.main
            assert provider.lines == (line,)
            assert line.line_id == LineId("tw:thsr:main")
            assert line.operator is LINE_CATALOG[line.line_id].operator
            assert line.operator.name == "台灣高速鐵路股份有限公司"
            assert line.status is status
            assert line.updated_at == (datetime.fromisoformat(updated) if updated else None)
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            if status is LineStatus.NORMAL:
                assert not provider.alerts and not provider.affected_lines
            else:
                assert len(provider.alerts) == 1
                alert = provider.alerts[0]
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.language == "zh-Hant" and alert.source_url == _URL
                assert "發生原因：" in alert.description and "影響路段：" in alert.description
                assert alert.effect is (AlertEffect.DELAYS if status is LineStatus.DELAYED else AlertEffect.OTHER)
                assert alert.active_from is None and alert.active_until is None
            if fixture == "thsr_20250227055330.html":
                assert "彰化-南港" in provider.alerts[0].description
            if fixture == "thsr_20241003073858.html":
                assert "台中以南暫停營運" in provider.alerts[0].description
                assert "10/2" not in provider.alerts[0].description  # collapsed old update
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "unknown_label", "unknown_marker", "conflicting_marker",
])
def test_synthetic_unknown_state_is_preserved(mutation: str) -> None:
    html = _html()
    if mutation == "unknown_label":
        html = html.replace("全線正常營運", "未知的營運狀態")
    elif mutation == "unknown_marker":
        html = html.replace('class="ts-tag normal"', 'class="ts-tag future"')
    else:
        html = html.replace('class="ts-tag normal"', 'class="ts-tag caution"')

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = ThsrProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.alerts[0].description == provider.main.source_status
            assert provider.alerts[0].effect is AlertEffect.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "panel", "duplicate_panel", "card", "label", "details", "body", "time", "invalid_time", "cause",
])
def test_synthetic_malformed_html_keeps_previous_snapshot(mutation: str) -> None:
    original = _html("thsr_20240403005339.html")
    soup = BeautifulSoup(original, "html.parser")
    selectors = {
        "panel": ".trafficstatus-container", "card": ".ts-tag", "label": ".status-ds",
        "details": ".status-detail", "body": ".status-detail > p",
        "time": ".status-detail > span", "cause": ".status-remark > li",
    }
    if mutation == "duplicate_panel":
        html = original + original
    elif mutation == "invalid_time":
        html = original.replace("2024/04/03 08:33", "2024/99/03 08:33")
    else:
        element = soup.select_one(selectors[mutation])
        assert element is not None
        element.decompose()
        html = str(soup)
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html if broken else original)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ThsrProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.main.status is LineStatus.DELAYED

    asyncio.run(scenario())


def test_synthetic_recovery_clears_incident_and_update_time() -> None:
    recovering = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_html(
            "thsr_normal.html" if recovering else "thsr_20240403005339.html",
        ))

    async def scenario() -> None:
        nonlocal recovering
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ThsrProvider(client=client)
            await provider.refresh()
            old = provider.main
            recovering = True
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.delay_lines
            assert provider.main.updated_at is None
            assert old.status is LineStatus.DELAYED and old.alerts

    asyncio.run(scenario())


def test_synthetic_multiple_current_incidents_and_links() -> None:
    # Combine two independent real cards; this combined page is synthetic.
    soup = BeautifulSoup(_html("thsr_20240403005339.html"), "html.parser")
    other = BeautifulSoup(_html("thsr_20250227055330.html"), "html.parser").select_one(".ts-tag")
    row = soup.select_one(".row")
    assert row is not None and other is not None
    row.append(other)
    body = other.select_one(".status-detail > p")
    assert body is not None
    link = soup.new_tag("a", href="/ArticleContent/example")
    link.string = "詳細資訊"
    body.append(link)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = ThsrProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.DELAYED
            assert len(provider.alerts) == 2
            assert provider.main.updated_at == datetime.fromisoformat("2025-02-27T13:49:00+08:00")
            assert "https://www.thsrc.com.tw/ArticleContent/example" in provider.alerts[1].description

    asyncio.run(scenario())


def test_tracker_registration_and_failed_refresh_isolation() -> None:
    failing = False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.thsrc.com.tw":
            return httpx.Response(503) if failing else httpx.Response(200, text=_html())
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal failing
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ThsrProvider(client=client)
            tracker = Tracker(enabled_providers=("thsr", "hankyu"), overrides=(provider,), client=client)
            assert tracker.thsr is provider
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            await tracker.refresh()
            previous = provider.lines
            failing = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("thsr")}
            assert isinstance(captured.value.errors[ProviderId("thsr")], FetchError)
            assert provider.lines is previous
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
            assert not client.is_closed
        assert any(p.provider_id == ProviderId("thsr") for p in Tracker().providers)
        assert Tracker(enabled_providers=("thsr",)).lines[0].line_id == LineId("tw:thsr:main")

    asyncio.run(scenario())
