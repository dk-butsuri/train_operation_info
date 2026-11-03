"""Live Yahoo DOM excerpts; mutations below are explicitly synthetic cases."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import LINE_CATALOG, LineId, LineScope, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.yahoo import YahooArea, YahooProvider, YahooRouteId
from train_operation_info.providers.yahoo.provider import _BINDINGS, _announced_at, _parse_area, _parse_detail
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"
_NOW = datetime(2026, 11, 2, 0, 30, tzinfo=timezone(timedelta(hours=9)))


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _handler(request: httpx.Request) -> httpx.Response:
    key = request.url.path.removeprefix("/diainfo/").replace("/", "_")
    assert request.url.host == "transit.yahoo.co.jp"
    return httpx.Response(200, text=_fixture(f"yahoo_{key}.html"))


class _RecordedYahoo(YahooProvider):
    @staticmethod
    def _now() -> datetime:
        return _NOW


def test_full_nationwide_refresh_and_shared_identity() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
            provider = _RecordedYahoo(client=client)
            tracker = Tracker(enabled_providers=("yahoo",), overrides=(provider,))
            await tracker.refresh()
            assert len(provider.source_line_ids) == 536
            assert len(provider.lines) == 532
            assert not provider.unknown_lines
            assert len(provider.delay_lines) == 9
            assert provider.midosuji.status is LineStatus.NORMAL
            assert provider.bantan.status is LineStatus.DELAYED
            kyoto = provider.get_source_line(YahooRouteId("288/0"))
            assert kyoto is not None and kyoto.status is LineStatus.SUSPENDED
            assert kyoto.line_id == tracker.kintetsu.kyoto.line_id
            assert provider.midosuji.line_id == tracker.osaka_metro.midosuji.line_id
            assert provider.midosuji is not tracker.osaka_metro.midosuji
            assert tracker.osaka_metro.midosuji.fetched_at is None
            assert provider.midosuji.updated_at is None
            assert tracker.lines == provider.lines
            assert tracker.delay_lines == provider.delay_lines
            assert all(line.fetched_at == _NOW for line in provider.lines)
            assert all(line.line_id in LINE_CATALOG for line in provider.lines)
            assert all(line.source_line_names for line in provider.lines)
            assert all(line.updated_at is None or line.updated_at.utcoffset() is not None for line in provider.lines)
            assert all(alert.source_url.startswith("https://transit.yahoo.co.jp/diainfo/") for alert in provider.alerts)
            assert provider.bantan.updated_at == datetime(2026, 11, 1, 22, 5, tzinfo=_NOW.tzinfo)
            assert provider.get_source_line(YahooRouteId("331/421")) is provider.get_source_line(YahooRouteId("331/422"))
            assert provider.get_source_line(YahooRouteId("9/9")) is not provider.get_source_line(YahooRouteId("9/10"))
            assert provider.get_source_line(YahooRouteId("unknown/0")) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("source_id", "fixture", "expected", "published"),
    [
        ("336/0", "336", "列車遅延", True),
        ("288/0", "288", "運転見合わせ", True),
        ("547/0", "547", "平常運転", True),
        ("321/0", "321", "平常運転", False),
    ],
)
def test_real_detail_states(source_id: str, fixture: str, expected: str, published: bool) -> None:
    binding = next(item for item in _BINDINGS if item.source_id == source_id)
    detail = _parse_detail(_fixture(f"yahoo_evidence_{fixture}.html"), binding, _NOW)
    assert detail.status == expected
    assert (detail.updated_at is not None) == published
    assert detail.description
    if detail.updated_at is not None:
        assert detail.updated_at.utcoffset() == timedelta(hours=9)


@pytest.mark.parametrize("area", list(YahooArea))
def test_real_area_requires_full_registered_coverage(area: YahooArea) -> None:
    html = _fixture(f"yahoo_area_{area.value}.html")
    rows = _parse_area(html, area)
    assert rows
    # A truncated successful HTTP response must never imply normal service.
    soup = BeautifulSoup(html, "html.parser")
    row = soup.select_one("tr:has(td)")
    assert row is not None
    row.decompose()
    with pytest.raises(ParseError, match="coverage"):
        _parse_area(str(soup), area)


def test_scope_and_reuse_of_existing_kintetsu_and_nankai_ids() -> None:
    tracker = Tracker()
    for source, official in (
        ("284/0", tracker.kintetsu.osaka), ("288/0", tracker.kintetsu.kyoto),
        ("339/0", tracker.nankai.main), ("346/0", tracker.nankai.koya),
        ("347/0", tracker.nankai.shiomibashi), ("348/0", tracker.nankai.semboku),
    ):
        yahoo = tracker.yahoo.get_source_line(YahooRouteId(source))
        assert yahoo is not None and yahoo.line_id == official.line_id
        assert yahoo.operator is official.operator
        assert yahoo is not official
    keihan = tracker.yahoo.get_source_line(YahooRouteId("300/0"))
    kintetsu = tracker.yahoo.get_source_line(YahooRouteId("237/0"))
    assert keihan is not None and keihan.scope is LineScope.GROUP
    assert kintetsu is not None and kintetsu.scope is LineScope.GROUP
    assert keihan.line_id != tracker.keihan.main.line_id
    assert tracker.yahoo.hankyu_kyoto.line_id != tracker.hankyu.kyoto.line_id


def test_yahoo_is_opt_in_with_terms_available_before_fetching() -> None:
    tracker = Tracker()
    assert all(provider.provider_id != ProviderId("yahoo") for provider in tracker.providers)
    assert all(line.provider_id != ProviderId("yahoo") for line in tracker.lines)
    metadata = tracker.yahoo.metadata
    assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert metadata.reviewed_at.utcoffset() is not None
    assert "H000007493" in str(metadata.additional_terms_urls[0])
    assert Tracker(enabled_providers=("yahoo",)).providers[0].provider_id == ProviderId("yahoo")
    # Injection alone does not opt a caller into fetching Yahoo.
    assert all(provider.provider_id != ProviderId("yahoo") for provider in Tracker(overrides=(YahooProvider(),)).providers)


def test_selected_area_keeps_unobserved_sections_unknown() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return _handler(request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _RecordedYahoo(areas=(YahooArea.KINKI,), client=client)
            await provider.refresh()
            assert provider.areas == (YahooArea.KINKI,)
            assert "/diainfo/area/6" in requests
            assert not any(path.startswith("/diainfo/area/") and path != "/diainfo/area/6" for path in requests)
            assert provider.midosuji.status is LineStatus.NORMAL
            assert provider.sanin.status is LineStatus.UNKNOWN
            assert "未取得の区間あり" in (provider.sanin.source_status or "")
            assert provider.sanin.source_line_names == ("山陰本線[園部～鳥取]",)
            assert provider.yamanote.fetched_at is None
            assert provider.yamanote.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "area", "detail"])
def test_failure_keeps_entire_previous_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            if failure == "http":
                return httpx.Response(503)
            if failure == "area" and "/area/" in request.url.path:
                return httpx.Response(200, text="<html>maintenance</html>")
            if failure == "detail" and "/area/" not in request.url.path:
                return httpx.Response(200, text="<div id='mdServiceStatus'></div>")
        return _handler(request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _RecordedYahoo(areas=(YahooArea.KINKI,), client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError if failure == "http" else ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.bantan.status is LineStatus.DELAYED

    asyncio.run(scenario())


def test_recovery_clears_previous_delay_and_unknown_label_is_preserved() -> None:
    mode = "delay"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/diainfo/336/0":
            html = _fixture("yahoo_evidence_336.html")
            if mode == "recovery":
                html = html.replace("列車遅延", "平常運転")
            elif mode == "unknown":
                html = html.replace("列車遅延", "未知の状態")
            return httpx.Response(200, text=html)
        return _handler(request)

    async def scenario() -> None:
        nonlocal mode
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _RecordedYahoo(areas=(YahooArea.KINKI,), client=client)
            await provider.refresh()
            delayed = provider.bantan
            assert delayed.status is LineStatus.DELAYED
            mode = "recovery"
            await provider.refresh()
            # Synthetic current label overrides the earlier area table and old prose.
            recovered = provider.bantan
            assert recovered.status is LineStatus.NORMAL
            assert not recovered.alerts
            mode = "unknown"
            await provider.refresh()
            unknown = provider.bantan
            assert unknown.status is LineStatus.UNKNOWN
            assert unknown.source_status == "未知の状態"
            assert unknown.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["name", "operator", "url", "duplicate"])
def test_changed_route_identity_rejected(change: str) -> None:
    soup = BeautifulSoup(_fixture("yahoo_area_6.html"), "html.parser")
    link = soup.select_one("a[href*='/321/0']")
    assert link is not None
    if change == "name":
        link.string = "another route"
    elif change == "url":
        link["href"] = "https://example.com/diainfo/321/0"
    elif change == "operator":
        heading = link.find_previous("h3")
        assert isinstance(heading, Tag)
        heading.string = "another carrier"
    else:
        row = link.find_parent("tr")
        assert row is not None
        row.insert_after(BeautifulSoup(str(row), "html.parser"))
    with pytest.raises(ParseError):
        _parse_area(str(soup), YahooArea.KINKI)


def test_missing_published_time_is_not_invented() -> None:
    binding = next(item for item in _BINDINGS if item.source_id == "336/0")
    soup = BeautifulSoup(_fixture("yahoo_evidence_336.html"), "html.parser")
    for span in soup.select("#mdServiceStatus dd p span"):
        span.decompose()
    with pytest.raises(ParseError, match="timestamp"):
        _parse_detail(str(soup), binding, _NOW)


def test_publication_year_rollover_and_invalid_dates() -> None:
    now = datetime(2027, 1, 1, 0, 2, tzinfo=_NOW.tzinfo)
    assert _announced_at(12, 31, 23, 55, now).year == 2026
    assert _announced_at(1, 1, 0, 5, now).year == 2027
    assert _announced_at(2, 29, 5, 0, now).year == 2024
    with pytest.raises(ParseError):
        _announced_at(2, 30, 5, 0, now)
    with pytest.raises(ValueError, match="timezone"):
        _announced_at(1, 1, 0, 0, datetime(2027, 1, 1))


def test_selection_validation() -> None:
    with pytest.raises(ValueError):
        YahooProvider(areas=())
    with pytest.raises(ValueError):
        YahooProvider(areas=(YahooArea.KINKI, YahooArea.KINKI))
    with pytest.raises(ValueError):
        YahooProvider(max_concurrency=0)
