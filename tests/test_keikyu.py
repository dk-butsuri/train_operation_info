"""Real Keikyu notices/recovery and explicitly synthetic broken responses."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, LineId, LineStatus, ProviderId, UsagePermission,
)
from train_operation_info.providers.keikyu import KeikyuProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://unkou.keikyu.co.jp/"
_LINE_IDS = (
    LineId("jp:keikyu:line_78db092fdebd"),
    LineId("jp:keikyu:line_f7fdfd13f776"),
    LineId("jp:keikyu:line_f45aa080b06c"),
    LineId("jp:keikyu:line_1baf033c4c82"),
    LineId("jp:keikyu:line_298c2fc57ddd"),
)


def _html(name: str) -> bytes:
    return (_FIXTURES / f"keikyu_{name}.html").read_bytes()


def test_live_fixture_is_normal_across_all_five_lines() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_html("normal")),
        )) as client:
            provider = KeikyuProvider(client=client)
            assert len(provider.unknown_lines) == 5
            await provider.refresh()
            assert len(provider.lines) == 5
            assert {line.line_id for line in provider.lines} == set(_LINE_IDS)
            for line in provider.lines:
                assert line.status is LineStatus.NORMAL
                assert line.source_status == "京急線は平常通り運転しています。"
                assert line.alerts == ()
                assert line.provider_id == ProviderId("keikyu") and line.source_url == _URL
                assert line.operator.name == "京浜急行電鉄"
                assert line.updated_at is not None and line.updated_at.isoformat() == "2026-11-03T00:29:00+09:00"
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert provider.main.line_id == LineId("jp:keikyu:line_78db092fdebd")
            assert provider.airport.line_id == LineId("jp:keikyu:line_f7fdfd13f776")
            assert provider.daishi.line_id == LineId("jp:keikyu:line_f45aa080b06c")
            assert provider.kurihama.line_id == LineId("jp:keikyu:line_1baf033c4c82")
            assert provider.zushi.line_id == LineId("jp:keikyu:line_298c2fc57ddd")
            assert not provider.alerts and not client.is_closed
    asyncio.run(scenario())


@pytest.mark.parametrize(("capture", "updated", "keyword"), [
    ("20220713030847", "2022-07-13T11:44:00+09:00", "金沢文庫"),
    ("20250730013943", "2025-07-30T10:29:00+09:00", "津波警報"),
])
def test_archived_notices_leave_every_line_unknown_with_unspecified_scope(
    capture: str, updated: str, keyword: str,
) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_html(capture)),
        )) as client:
            provider = KeikyuProvider(client=client)
            await provider.refresh()
            for line in provider.lines:
                assert line.status is LineStatus.UNKNOWN
                assert line.updated_at is not None and line.updated_at.isoformat() == updated
            alert, = provider.alerts
            assert alert.effect is AlertEffect.UNKNOWN
            assert keyword in alert.description
            assert alert.affected_line_ids == ()
            assert alert.timing is AlertTiming.UNKNOWN
            assert alert.active_from is None and alert.active_until is None
            assert provider.unclassified_alerts == (alert,)
            assert not provider.affected_lines and not provider.delay_lines
            assert len(provider.unknown_lines) == 5
            # Every line's alerts resolve to the same single notice object.
            assert len({id(a) for line in provider.lines for a in line.alerts}) == 1
    asyncio.run(scenario())


def test_real_suspension_then_normal_clears_notice_on_every_line() -> None:
    html = _html("20250730013943")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            tracker = Tracker(enabled_providers=("keikyu",), client=client)
            await tracker.refresh()
            previous = tracker.keikyu.zushi
            assert tracker.alerts and previous.status is LineStatus.UNKNOWN
            html = _html("normal")
            await tracker.refresh()
            for line in tracker.keikyu.lines:
                assert line.status is LineStatus.NORMAL
                assert not line.alerts
            assert not tracker.alerts and not tracker.affected_lines
    asyncio.run(scenario())


def test_synthetic_mixed_and_unknown_notices_are_retained() -> None:
    async def scenario() -> None:
        for body, expected in (
            ("京急線は平常通り運転しています。合成テスト：明日の運行にご注意ください。", LineStatus.UNKNOWN),
            ("合成テスト：新しい形式の運行案内です。", LineStatus.UNKNOWN),
        ):
            soup = BeautifulSoup(_html("normal"), "html.parser")
            dd = soup.select_one("dl.index_unit dd")
            assert dd is not None
            dd.string = body
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=str(soup).encode("utf-8")),
            )) as client:
                provider = KeikyuProvider(client=client)
                await provider.refresh()
                assert all(line.status is expected for line in provider.lines)
                assert provider.alerts[0].description == body
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_unit", "duplicate_unit", "missing_header", "wrong_header",
    "missing_dt", "duplicate_dt", "missing_dd", "invalid_date", "impossible_date", "empty_body",
])
def test_synthetic_malformed_html_preserves_previous_notice(mutation: str) -> None:
    soup = BeautifulSoup(_html("20220713030847"), "html.parser")
    unit = soup.select_one("dl.index_unit")
    dt = soup.select_one("dl.index_unit dt")
    header = soup.select_one("h1.heading_title")
    assert unit is not None and dt is not None and header is not None
    if mutation == "missing_unit":
        unit.decompose()
    elif mutation == "duplicate_unit":
        unit.insert_after(BeautifulSoup(str(unit), "html.parser"))
    elif mutation == "missing_header":
        header.decompose()
    elif mutation == "wrong_header":
        header.string = "別の運行情報"
    elif mutation == "missing_dt":
        dt.decompose()
    elif mutation == "duplicate_dt":
        dt.insert_after(BeautifulSoup(str(dt), "html.parser"))
    elif mutation == "missing_dd":
        for dd in unit.select("dd"):
            dd.decompose()
    elif mutation == "invalid_date":
        dt.string = "11:44更新"
    elif mutation == "impossible_date":
        dt.string = "2022/13/40 11:44更新"
    else:
        for dd in unit.select("dd"):
            dd.clear()
    html = _html("20220713030847")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = KeikyuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = str(soup).encode("utf-8")
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous and provider.alerts
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_selection_injection_and_failure_isolation(failure: str) -> None:
    requests: list[str] = []
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            if broken:
                if failure == "connection":
                    raise httpx.ConnectError("synthetic failure", request=request)
                return httpx.Response(503)
            return httpx.Response(200, content=_html("20220713030847"))
        raise AssertionError(f"Unexpected request: {request.url}")

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeikyuProvider(client=client)
            disabled = Tracker(enabled_providers=(), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("keikyu",), client=client, overrides=(provider,))
            assert tracker.keikyu is provider and tracker.providers == (provider,)
            await tracker.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("keikyu")}
            assert isinstance(captured.value.errors[ProviderId("keikyu")], FetchError)
            assert provider.lines is previous and provider.alerts
    asyncio.run(scenario())


def test_canonical_routes_are_independent_and_metadata_is_reviewed() -> None:
    tracker = Tracker()
    provider = tracker.keikyu
    assert provider in tracker.providers
    for line_id in _LINE_IDS:
        official = provider.get_line(line_id)
        assert official is not None
        yahoo = tracker.yahoo.get_line(line_id)
        if yahoo is not None:
            assert official is not yahoo and official.operator == yahoo.operator
    assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(provider.metadata.terms_url) == "https://www.keikyu.co.jp/website-guide.html"
    assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
    assert "固く禁じます" in provider.metadata.usage_note
