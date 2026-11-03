"""Official Keisei DOM captures; notice mutations and faults are synthetic."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, LineScope, LineStatus, ProviderId, UsagePermission,
)
from train_operation_info.providers.keisei import KeiseiProvider
from train_operation_info.providers.keisei.provider import _parse_notice
from train_operation_info.providers.yahoo import YahooProvider, YahooRouteId

_FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (_FIXTURES / f"keisei_{name}").read_text(encoding="utf-8")


@pytest.mark.parametrize(("fixture", "delayed", "suspended", "partial"), [
    ("normal", 0, 0, 0),
    ("20260903013656", 0, 0, 0),
    ("20260415104003", 2, 1, 0),
    ("20260516001941", 1, 0, 1),
    ("20260813101347", 6, 0, 0),
    ("20261016114304", 3, 0, 0),
])
def test_official_status_scope_and_details(fixture: str, delayed: int, suspended: int, partial: int) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "www.keisei.co.jp"
            assert request.url.path in ("/traininfo/index.php", "/traininfo/data/notice.js")
            name = "notice.js" if request.url.path.endswith(".js") else f"{fixture}.html"
            return httpx.Response(200, text=_fixture(name))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeiseiProvider(client=client)
            initial_unknown = provider.unknown_lines
            assert len(initial_unknown) == 6
            await provider.refresh()
            assert len(provider.lines) == 6
            assert len(provider.delay_lines) == delayed
            assert sum(l.status is LineStatus.SUSPENDED for l in provider.lines) == suspended
            assert sum(l.status is LineStatus.PARTIAL_SUSPENSION for l in provider.lines) == partial
            assert len(provider.unknown_lines) == 0
            assert provider.chiba_chihara.scope is LineScope.GROUP
            assert provider.matsudo.operator.name == "京成電鉄"
            assert all(l.operator is LINE_CATALOG[l.line_id].operator for l in provider.lines)
            assert all(l.fetched_at is not None and l.fetched_at.utcoffset() == timedelta(0) for l in provider.lines)
            assert all(l.updated_at is None for l in provider.lines)
            if suspended:
                alert = provider.main.alerts[0]
                assert alert.effect is AlertEffect.NO_SERVICE
                assert alert.affected_line_ids == (provider.main.line_id,)
                assert "八千代台 ～ 京成佐倉" in alert.description
                assert "踏切内接触事故" in alert.description
                assert "【押上線" not in alert.description
            if partial:
                assert provider.oshiage.alerts[0].effect is AlertEffect.REDUCED_SERVICE
                assert provider.main.status is LineStatus.DELAYED
            if fixture == "20260813101347":
                assert provider.chiba_chihara.status is LineStatus.DELAYED
                assert provider.matsudo.status is LineStatus.DELAYED
            assert not client.is_closed

    asyncio.run(scenario())


def test_tracker_injection_selection_recovery_and_yahoo_identity() -> None:
    fixture = "20260415104003.html"
    requests: list[str] = []

    async def scenario() -> None:
        nonlocal fixture
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(200, text=_fixture("notice.js" if request.url.path.endswith(".js") else fixture))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeiseiProvider(client=client)
            tracker = Tracker(enabled_providers=("keisei",), overrides=(provider,))
            assert tracker.keisei is provider and tracker.providers == (provider,)
            assert requests == []
            await tracker.refresh()
            old = provider.main
            assert len(requests) == 2
            assert all("keisei.co.jp/traininfo/" in url for url in requests)
            fixture = "normal.html"
            await tracker.refresh()
            assert old.status is LineStatus.SUSPENDED
            assert tracker.alerts == () and tracker.affected_lines == ()
            assert all(l.status is LineStatus.NORMAL for l in tracker.lines)
            yahoo = YahooProvider()
            for official, source in [(provider.main, "96/0"), (provider.narita_sky_access, "622/0"),
                                     (provider.oshiage, "98/0"), (provider.kanamachi, "101/0"),
                                     (provider.chiba_chihara, "99/0"), (provider.matsudo, "127/0")]:
                other = yahoo.get_source_line(YahooRouteId(source))
                assert other is not None and other.line_id == official.line_id
                assert other is not official and other.status is LineStatus.UNKNOWN
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED

    asyncio.run(scenario())


def test_injected_but_disabled_provider_never_fetches() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"Unexpected request: {request.url}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeiseiProvider(client=client)
            tracker = Tracker(enabled_providers=(), overrides=(provider,))
            await tracker.refresh()
            assert tracker.lines == () and len(provider.unknown_lines) == 6

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "missing_section", "empty_section", "duplicate_section", "duplicate_route", "unknown_route",
    "missing_heading", "missing_details", "missing_body", "missing_body_route", "unknown_body_route",
    "empty_body", "conflicting_normal", "notice_structure", "notice_network", "page_network",
])
def test_synthetic_failure_preserves_complete_snapshot(fault: str) -> None:
    soup = BeautifulSoup(_fixture("20261016114304.html"), "html.parser")
    selectors = {
        "missing_section": "#info_dif", "empty_section": "#info_dif > .ja",
        "missing_heading": "#info_dif > .ja dt", "missing_details": "#info_dif > .ja dl:first-child dd",
        "missing_body": "#info_txt",
    }
    if fault in selectors:
        node = soup.select_one(selectors[fault])
        assert node is not None
        if fault == "empty_section":
            node.clear()
        elif fault == "missing_details":
            for detail in soup.select("#info_dif > .ja dl:first-child dd"):
                detail.decompose()
        else:
            node.decompose()
    elif fault in ("duplicate_section", "duplicate_route"):
        node = soup.select_one("#info_dif > .ja" if fault == "duplicate_section" else "#info_dif > .ja dl")
        parent = soup.select_one("#info_dif" if fault == "duplicate_section" else "#info_dif > .ja")
        assert node is not None and parent is not None
        parent.append(BeautifulSoup(str(node), "html.parser"))
    elif fault == "unknown_route":
        node = soup.select_one("#info_dif > .ja dt")
        assert node is not None
        node.string = "未登録線　遅れ"
    elif fault in ("unknown_body_route", "empty_body", "missing_body_route"):
        node = soup.select_one("#info_txt > #jp_txt")
        assert node is not None
        text = node.get_text("\n", strip=True)
        node.string = (text.replace("成田スカイアクセス線", "未登録線") if fault == "unknown_body_route" else
                       text[:text.index("【京成本線")] if fault == "missing_body_route" else "")
    elif fault == "conflicting_normal":
        normal = BeautifulSoup(_fixture("normal.html"), "html.parser").select_one("#info_dif > .ja dl")
        parent = soup.select_one("#info_dif > .ja")
        assert normal is not None and parent is not None
        parent.append(normal)
    broken = False

    async def scenario() -> None:
        nonlocal broken
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(".js"):
                if broken and fault == "notice_network":
                    return httpx.Response(503)
                return httpx.Response(200, text="bad script" if broken and fault == "notice_structure" else _fixture("notice.js"))
            if broken and fault == "page_network":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(200, text=str(soup) if broken else _fixture("20261016114304.html"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("keisei",), client=client)
            await tracker.refresh()
            previous = tracker.keisei.lines
            broken = True
            with pytest.raises(RefreshError) as error:
                await tracker.refresh()
            expected = FetchError if fault.endswith("network") else ParseError
            assert isinstance(error.value.errors[ProviderId("keisei")], expected)
            assert tracker.keisei.lines is previous

    asyncio.run(scenario())


def test_synthetic_unknown_status_preserves_source_text() -> None:
    text = _fixture("20261016114304.html").replace("京成本線　遅れ", "京成本線　新しい状態", 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, text=_fixture("notice.js") if request.url.path.endswith(".js") else text,
        ))) as client:
            provider = KeiseiProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.main.source_status == "新しい状態"
            assert "人身事故" in provider.main.alerts[0].description
            assert provider.main.alerts[0].effect is AlertEffect.UNKNOWN

    asyncio.run(scenario())


def test_synthetic_unknown_all_lines_statement_keeps_unscoped_alert() -> None:
    text = _fixture("normal.html").replace("京成線　平常運行", "京成線　新しい状態", 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, text=_fixture("notice.js") if request.url.path.endswith(".js") else text,
        ))) as client:
            provider = KeiseiProvider(client=client)
            await provider.refresh()
            assert len(provider.unknown_lines) == 6
            assert len(provider.alerts) == 1
            assert provider.alerts[0].affected_line_ids == ()
            assert "新しい状態" in provider.alerts[0].description

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["date", "interval", "missing_text", "flag", "duplicate_flag"])
def test_synthetic_invalid_notice_never_becomes_normal(change: str) -> None:
    script = """var ja_flg = 1;
var s_day = new Date('2026-11-02T09:00:00');
var e_day = new Date('2026-11-02T10:00:00');
var ja_txt = 'お知らせ';"""
    if change == "date":
        script = script.replace("2026-11-02T09:00:00", "invalid")
    elif change == "interval":
        script = script.replace("2026-11-02T10:00:00", "2026-11-01T10:00:00")
    elif change == "missing_text":
        script = script.replace("var ja_txt", "var other_txt")
    elif change == "flag":
        script = script.replace("ja_flg = 1", "ja_flg = 99")
    else:
        script += "var ja_flg = 0;"
    with pytest.raises((ParseError, ValueError)):
        _parse_notice(script, datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc))


def test_synthetic_notice_interval_timezone_and_unscoped_effect() -> None:
    script = """var ja_flg = 1;
var s_day = new Date('2026-11-02T09:00:00');
var e_day = new Date('2026-11-02T10:00:00');
var ja_txt = '【特定列車のお知らせ】<br />一部列車を運休します。';"""
    assert _parse_notice(script, datetime(2026, 11, 2, 0, tzinfo=timezone.utc)) is None
    assert _parse_notice(script, datetime(2026, 11, 2, 1, tzinfo=timezone.utc)) is None
    assert _parse_notice(script, datetime(2026, 11, 1, 23, tzinfo=timezone.utc)) is None
    assert _parse_notice(script, datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc)) is not None

    class RecordedKeisei(KeiseiProvider):
        @staticmethod
        def _now() -> datetime:
            return datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, text=script if request.url.path.endswith(".js") else _fixture("normal.html"),
        ))) as client:
            provider = RecordedKeisei(client=client)
            await provider.refresh()
            assert all(l.status is LineStatus.ALERT for l in provider.lines)
            assert len(provider.alerts) == 1 and provider.alerts[0].affected_line_ids == ()
            assert provider.alerts[0].effect is AlertEffect.OTHER

    asyncio.run(scenario())
