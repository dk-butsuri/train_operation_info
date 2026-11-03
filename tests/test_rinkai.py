"""Real Rinkai notices/recovery and explicitly synthetic broken responses."""

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
from train_operation_info.providers.rinkai import RinkaiProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://service.twr.co.jp/rinkai/public/information?lang=ja"


def _html(name: str = "normal") -> bytes:
    return (_FIXTURES / f"rinkai_{name}.html").read_bytes()


@pytest.mark.parametrize(("capture", "updated", "message"), [
    ("20180122093824", "2018-01-22T17:23:00+09:00", "大雪"),
    ("20180904125255", "2018-09-04T19:42:00+09:00", "架線への支障物"),
    ("20191012171221", "2019-10-12T14:31:00+09:00", "安全確認終了後"),
    ("20220825002322", "2022-08-25T08:15:00+09:00", "異音の確認"),
    ("20220926105254", "2022-09-26T18:51:00+09:00", "振替輸送"),
])
def test_archived_notices_keep_prose_and_explicit_update_time(
    capture: str, updated: str, message: str,
) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_html(capture)),
        )) as client:
            provider = RinkaiProvider(client=client)
            assert provider.unknown_lines == (provider.main,)
            await provider.refresh()
            line = provider.main
            assert line.line_id == LineId("jp:operator_a76aef032695:line_68e848012d4b")
            assert line.name == "りんかい線" and line.operator.name == "東京臨海高速鉄道"
            assert line.provider_id == ProviderId("rinkai") and line.source_url == _URL
            assert line.status is LineStatus.ALERT
            assert line.updated_at is not None and line.updated_at.isoformat() == updated
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            alert, = provider.alerts
            assert alert.effect is AlertEffect.OTHER
            assert message in alert.description
            assert "更新）" not in alert.description and "注意事項" not in alert.description
            assert line.source_status == alert.description
            assert alert.affected_line_ids == (line.line_id,)
            assert alert.timing is AlertTiming.UNKNOWN
            assert alert.active_from is None and alert.active_until is None
            assert provider.unclassified_alerts == (alert,)
            assert provider.affected_lines == (line,) and not provider.delay_lines
            assert not client.is_closed
    asyncio.run(scenario())


def test_real_delay_then_normal_clears_notice_and_update_date() -> None:
    html = _html("20220825002322")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            tracker = Tracker(enabled_providers=("rinkai",), client=client)
            await tracker.refresh()
            previous = tracker.rinkai.main
            assert tracker.alerts and previous.updated_at is not None
            for name in ("20220825005348", "normal"):
                html = _html(name)
                await tracker.refresh()
                line = tracker.rinkai.main
                assert line.status is LineStatus.NORMAL
                assert line.source_status == "平常通り運転しています。"
                assert line.updated_at is None  # #nowTime is not a distribution timestamp.
                assert not tracker.alerts and not tracker.affected_lines and not tracker.unknown_lines
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo.status is LineStatus.UNKNOWN
            assert previous.status is LineStatus.ALERT and previous.alerts
    asyncio.run(scenario())


def test_synthetic_contradictory_normal_and_unknown_notice_are_retained() -> None:
    async def scenario() -> None:
        for body, expected in (
            ("平常通り運転しています。合成テスト：明日の運行にご注意ください。", LineStatus.UNKNOWN),
            ("合成テスト：新しい形式の運行案内です。", LineStatus.ALERT),
        ):
            soup = BeautifulSoup(_html(), "html.parser")
            panel = soup.select_one("#serviceInfo")
            assert panel is not None
            panel.string = body
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=str(soup).encode("utf-8")),
            )) as client:
                provider = RinkaiProvider(client=client)
                await provider.refresh()
                assert provider.main.status is expected and provider.main.updated_at is None
                assert provider.alerts[0].description == body
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "outside_panel", "missing_header", "wrong_header",
    "missing_container", "duplicate_container", "empty_panel", "placeholder", "date_only",
    "duplicate_date", "invalid_date", "impossible_date", "hidden_only",
])
def test_synthetic_malformed_html_preserves_previous_notice(mutation: str) -> None:
    soup = BeautifulSoup(_html("20220825002322"), "html.parser")
    panel = soup.select_one("#serviceInfo")
    date = soup.select_one("p.date")
    header = soup.select_one("h1 img")
    container = soup.select_one(".contBodyPage")
    assert panel is not None and date is not None and header is not None and container is not None
    if mutation == "missing_panel":
        panel.decompose()
    elif mutation == "duplicate_panel":
        panel.insert_after(BeautifulSoup(str(panel), "html.parser"))
    elif mutation == "outside_panel":
        soup.append(panel.extract())
    elif mutation == "missing_header":
        header.decompose()
    elif mutation == "wrong_header":
        header["alt"] = "別会社の運行情報"
    elif mutation == "missing_container":
        container.unwrap()
    elif mutation == "duplicate_container":
        soup.append(soup.new_tag("div", attrs={"class": "contBodyPage"}))
    elif mutation == "empty_panel":
        panel.clear()
    elif mutation == "placeholder":
        panel.string = "-"
    elif mutation == "date_only":
        panel.clear()
        panel.append(date)
    elif mutation == "duplicate_date":
        date.insert_after(BeautifulSoup(str(date), "html.parser"))
    elif mutation == "invalid_date":
        date.string = "08:15"
    elif mutation == "impossible_date":
        date.string = "（2022年13月25日 08時15分更新）"
    else:
        panel.clear()
        script = soup.new_tag("script")
        script.string = "平常通り運転しています。"
        panel.append(script)
    html = _html("20220825002322")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = RinkaiProvider(client=client)
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
            return httpx.Response(200, content=_html("20220825002322"))
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RinkaiProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("rinkai", "hankyu"), client=client, overrides=(provider,))
            assert tracker.rinkai is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("rinkai")}
            assert isinstance(captured.value.errors[ProviderId("rinkai")], FetchError)
            assert provider.lines is previous and provider.alerts
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
    asyncio.run(scenario())


def test_canonical_route_is_independent_and_metadata_is_reviewed() -> None:
    tracker = Tracker()
    provider = tracker.rinkai
    assert provider in tracker.providers
    official = provider.main
    yahoo = tracker.yahoo.get_line(official.line_id)
    assert yahoo is not None and official is not yahoo and official.operator == yahoo.operator
    assert provider.metadata.usage_permission is UsagePermission.UNSPECIFIED
    assert provider.metadata.terms_url is None
    assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
    assert "official-account" in provider.metadata.usage_note
