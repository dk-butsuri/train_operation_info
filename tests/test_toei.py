"""Real normal HTML; incident, recovery and malformed responses are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.toei import ToeiProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html"


def _normal() -> bytes:
    return (_FIXTURES / "toei_normal.html").read_bytes()


def _synthetic(label: str, body: str) -> bytes:
    soup = BeautifulSoup(_normal(), "html.parser")
    summary = soup.select_one("dl.infoMita dd")
    route = soup.select_one("dt.routeMita")
    assert summary is not None and route is not None and route.parent is not None
    detail = route.parent.select_one(".operation__info")
    assert detail is not None
    summary.clear()
    summary.append(label)
    detail.clear()
    detail.append(BeautifulSoup(body, "html.parser"))
    return str(soup).encode("utf-8")


def test_live_normal_fixture_routes_metadata_and_independent_yahoo_state() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.method == "GET"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=_normal())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("toei",), client=client)
            provider = tracker.toei
            initial_unknown = provider.unknown_lines
            assert len(initial_unknown) == 4
            await tracker.refresh()
            assert requests == [_URL]
            assert provider.lines == (provider.asakusa, provider.mita, provider.shinjuku, provider.oedo)
            assert not provider.alerts and not provider.unknown_lines and not provider.affected_lines
            for line, name in zip(provider.lines, ("浅草線", "三田線", "新宿線", "大江戸線")):
                assert line.status is LineStatus.NORMAL
                assert line.source_status == "平常運行"
                assert line.source_line_names == (name,)
                assert line.updated_at is None  # The displayed clock is not an update.
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                assert line.provider_id == ProviderId("toei")
                assert line.operator.name == "東京都交通局"
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo is not line
                assert yahoo.operator == line.operator
                assert yahoo.status is LineStatus.UNKNOWN
            assert not client.is_closed
        assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
        assert str(provider.metadata.terms_url) == "https://www.kotsu.metro.tokyo.jp/riyo/"
        assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
        assert ProviderId("toei") in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "body", "expected"), [
    ("ダイヤ乱れ", "合成テスト：現在の案内。<br>以前は運転見合わせ。", LineStatus.ALERT),
    ("未確認の表示", "合成テスト：案内本文。", LineStatus.UNKNOWN),
    ("運転見合わせ", "合成テスト：全線の運休とは未確認。", LineStatus.UNKNOWN),
    ("平常運行", "合成テスト：本文と要約が矛盾。", LineStatus.UNKNOWN),
    ("ダイヤ乱れ", "現在、１５分以上の遅延はありません。", LineStatus.UNKNOWN),
    ("平常運行", "現在、１５分以上の遅延はありません。<br>追加案内", LineStatus.UNKNOWN),
])
def test_synthetic_incident_unknown_contradiction_and_recovery(
    label: str, body: str, expected: LineStatus,
) -> None:
    content = _synthetic(label, body + "<script>bad()</script><style>hidden</style>")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content),
        )) as client:
            provider = ToeiProvider(client=client)
            await provider.refresh()
            previous = provider.mita
            assert previous.status is expected
            assert previous.source_status == label
            alert, = previous.alerts
            assert alert.affected_line_ids == (previous.line_id,)
            assert "bad()" not in alert.description and "hidden" not in alert.description
            assert "<br>" not in alert.description
            if "<br>" in body:
                assert "\n" in alert.description
            assert provider.delay_lines == ()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines if line is not previous)
            content = _normal()
            await provider.refresh()
            assert provider.mita.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.affected_lines and not provider.unknown_lines
            assert previous.alerts == (alert,)

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_route", "duplicate_route", "unknown_route", "wrong_name", "wrong_link",
    "missing_body", "duplicate_body", "empty_body", "missing_summary", "duplicate_summary",
    "empty_label", "wrong_summary_name", "missing_panel", "duplicate_panel", "challenge",
])
def test_synthetic_invalid_response_preserves_previous_snapshot(mutation: str) -> None:
    soup = BeautifulSoup(_normal(), "html.parser")
    records = soup.select(".operation__item")
    bodies = soup.select(".operation__info")
    summaries = soup.select("dl.infoMita")
    if mutation == "missing_route":
        records[0].decompose()
    elif mutation == "duplicate_route":
        records[0].insert_after(BeautifulSoup(str(records[0]), "html.parser"))
    elif mutation == "unknown_route":
        records[0].select("dt")[0]["class"] = "route routeUnknown"
    elif mutation == "wrong_name":
        records[0].select("dt")[0].string = "未登録線"
    elif mutation == "wrong_link":
        records[0].select("a")[0]["href"] = "/subway/schedule/mita_log.html"
    elif mutation == "missing_body":
        bodies[0].decompose()
    elif mutation == "duplicate_body":
        bodies[0].insert_after(BeautifulSoup(str(bodies[0]), "html.parser"))
    elif mutation == "empty_body":
        bodies[0].clear()
        bodies[0].append(BeautifulSoup("<script>bad()</script>", "html.parser"))
    elif mutation == "missing_summary":
        summaries[0].decompose()
    elif mutation == "duplicate_summary":
        summaries[0].insert_after(BeautifulSoup(str(summaries[0]), "html.parser"))
    elif mutation == "empty_label":
        summaries[0].select("dd")[0].clear()
    elif mutation == "wrong_summary_name":
        summaries[0].select("dt")[0].string = "浅草線"
    elif mutation == "missing_panel":
        soup.select(".operation")[0].decompose()
    elif mutation == "duplicate_panel":
        panel = soup.select(".operation")[0]
        panel.insert_after(BeautifulSoup(str(panel), "html.parser"))
    content = _synthetic("ダイヤ乱れ", "合成テスト：案内本文。")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content),
        )) as client:
            provider = ToeiProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            content = b"<html>Request unsuccessful</html>" if mutation == "challenge" else str(soup).encode()
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_selection_injection_and_http_failure_isolation() -> None:
    requests: list[str] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            return httpx.Response(503 if fail else 200, content=_normal())
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ToeiProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), overrides=(provider,), client=client)
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("toei", "hankyu"), overrides=(provider,), client=client)
            assert tracker.toei is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("toei")}
            assert isinstance(captured.value.errors[ProviderId("toei")], FetchError)
            assert provider.lines is previous
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL

    asyncio.run(scenario())
