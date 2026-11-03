"""Official JR Shikoku fixtures; explicitly synthetic failure/unknown cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, LineStatus, UsagePermission
from train_operation_info.providers.jrshikoku import JrShikokuProvider
from train_operation_info.providers.yahoo import YahooProvider

_FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (_FIXTURES / f"jrshikoku_{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(("fixture", "affected"), [
    ("normal", 0), ("20250216210138", 1), ("20260712052626", 1),
    ("20240621132151", 10), ("20260116145742", 2),
])
def test_official_fixtures(fixture: str, affected: int) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=_html(fixture)),
        )) as client:
            provider = JrShikokuProvider(client=client)
            assert len(provider.unknown_lines) == 10
            await provider.refresh()
            assert len(provider.lines) == 10
            assert len(provider.affected_lines) == affected
            assert not provider.unknown_lines
            assert not provider.delay_lines
            for line in provider.lines:
                assert line.line_id in LINE_CATALOG
                assert line.operator.name == "JR四国"
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                if line.alerts:
                    assert line.status is LineStatus.ALERT
                    assert line.updated_at is not None and line.updated_at.utcoffset() == timedelta(hours=9)
                else:
                    assert line.status is LineStatus.NORMAL and line.updated_at is None
            if fixture == "20250216210138":
                assert provider.affected_lines == (provider.seto_ohashi,)
                assert "マリンライナー１号" in provider.alerts[0].description
                assert provider.alerts[0].affected_line_ids == (provider.seto_ohashi.line_id,)
                assert provider.seto_ohashi.updated_at is not None
                assert provider.seto_ohashi.updated_at.isoformat() == "2025-02-17T05:57:00+09:00"
            elif fixture == "20260712052626":
                assert provider.affected_lines == (provider.yodo,)
                assert "窪川駅～江川崎駅間" in provider.alerts[0].description
                assert "代行輸送について" in provider.alerts[0].description
            elif fixture == "20240621132151":
                assert len(provider.alerts) == 1
                assert provider.alerts[0].affected_line_ids == ()
            elif fixture == "20260116145742":
                assert {line.line_id for line in provider.affected_lines} == {
                    provider.yosan_takamatsu_matsuyama.line_id,
                    provider.yosan_matsuyama_uwajima.line_id,
                }
                # Future works in the body do not imply a current suspension.
                assert all(line.status is LineStatus.ALERT for line in provider.affected_lines)
            assert not client.is_closed
    asyncio.run(scenario())


def test_later_official_normal_clears_old_incident() -> None:
    html = _html("20260712052626")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            previous = provider.yodo
            html = _html("normal")
            await provider.refresh()
            assert previous.status is LineStatus.ALERT
            assert provider.yodo.status is LineStatus.NORMAL
            assert provider.yodo.updated_at is None
            assert not provider.alerts
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_map", "duplicate_map", "missing_body", "empty_body", "missing_time",
    "invalid_time", "missing_detail", "mismatched_id", "duplicate_id", "normal_conflict",
    "orphan_overlay", "maintenance",
])
def test_synthetic_malformed_response_preserves_incident(mutation: str) -> None:
    html = _html("20260712052626")
    soup = BeautifulSoup(html, "html.parser")
    if mutation == "maintenance":
        broken = "<html>Maintenance</html>"
    else:
        selectors = {"missing_map": ".ml_yodo", "missing_body": ".detail_txt",
                     "missing_time": ".upd_time", "missing_detail": ".delay_info dd"}
        if mutation in selectors:
            tag = soup.select_one(selectors[mutation])
            assert tag is not None
            tag.decompose()
        elif mutation == "duplicate_map":
            tag = soup.select_one(".ml_yodo")
            assert tag is not None and tag.parent is not None
            tag.parent.append(BeautifulSoup(str(tag), "html.parser"))
        elif mutation in ("empty_body", "invalid_time", "mismatched_id"):
            tag = soup.select_one({"empty_body": ".detail_txt", "invalid_time": ".upd_time",
                                   "mismatched_id": "dd"}[mutation])
            assert tag is not None
            if mutation == "mismatched_id":
                tag["dinfo_id"] = "other"
            else:
                tag.string = "" if mutation == "empty_body" else "2026/99/12 14:00更新"
        elif mutation == "duplicate_id":
            listing = soup.select_one(".delay_info dl")
            assert listing is not None
            listing.append(BeautifulSoup(str(listing.select_one("dt")) + str(listing.select_one("dd")), "html.parser"))
        elif mutation == "normal_conflict":
            tag = soup.select_one(".delay_status a")
            assert tag is not None
            tag.string = "現在、遅れ等の情報はありません。"
            tag["class"] = "nodelay"
        else:
            tag = soup.select_one(".ml_seto")
            assert tag is not None
            tag["style"] = "display:block;"
        broken = str(soup)

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = broken
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["summary", "heading", "style"])
def test_synthetic_unknown_display_retains_raw_text(mutation: str) -> None:
    html = _html("20260712052626")
    if mutation == "summary":
        html = html.replace("遅れまたは運転を見合わせている区間があります。", "未知の状態")
    elif mutation == "heading":
        html = html.replace("予土線", "未知路線")
    else:
        html = html.replace("display:block;", "display:unknown;")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            assert provider.yodo.status is LineStatus.UNKNOWN
            assert any("unknown" in a.description or "未知" in a.title for a in provider.alerts)
    asyncio.run(scenario())


def test_synthetic_multiple_notices_do_not_clear_affected_section() -> None:
    # Append the unscoped weather advisory to a real Yodo incident.
    soup = BeautifulSoup(_html("20260712052626"), "html.parser")
    listing = soup.select_one(".delay_info dl")
    assert listing is not None
    other = BeautifulSoup(_html("20240621132151"), "html.parser")
    for tag in other.select(".delay_info dt, .delay_info dd"):
        listing.append(tag)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            assert len(provider.yodo.alerts) == 2
            assert len(provider.alerts) == 2
            assert any(a.affected_line_ids == (provider.yodo.line_id,) for a in provider.yodo.alerts)
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "network"])
def test_fetch_failure_retains_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            if failure == "network":
                raise httpx.ConnectError("Synthetic outage", request=request)
            return httpx.Response(503)
        return httpx.Response(200, text=_html("20260712052626"))

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous
    asyncio.run(scenario())


def test_tracker_selection_dependency_injection_and_common_ids() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url) == "https://www.jr-shikoku.co.jp/info/index.html"
        return httpx.Response(200, text=_html("normal"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrShikokuProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not calls
            tracker = Tracker(enabled_providers=("jrshikoku",), overrides=(provider,))
            assert tracker.jrshikoku is provider
            await tracker.refresh()
            assert len(calls) == 1
            assert tracker.lines == provider.lines
            assert tracker.providers == (provider,)
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            yahoo = YahooProvider()
            for line in provider.lines:
                other = yahoo.get_line(line.line_id)
                assert other is not None and other is not line
                assert other.operator == line.operator and other.status is LineStatus.UNKNOWN
            assert any(p.provider_id == provider.provider_id for p in Tracker().providers)
    asyncio.run(scenario())


def test_tracker_other_failure_does_not_prevent_jrshikoku_refresh() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (httpx.Response(200, text=_html("normal")) if request.url.host == "www.jr-shikoku.co.jp"
                else httpx.Response(503))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("jrshikoku", "jrw"), client=client)
            with pytest.raises(RefreshError):
                await tracker.refresh()
            assert not tracker.jrshikoku.unknown_lines
            assert tracker.jrw.provider_id in tracker.refresh_errors
    asyncio.run(scenario())
