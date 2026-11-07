"""Official Shift_JIS excerpts and explicitly synthetic edge cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertTiming, LINE_CATALOG, LineId, LineStatus, ProviderId
from train_operation_info.providers.kintetsu import KintetsuProvider
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"
_NORMAL = "kintetsu_20260213065943.html"
_PARTIAL = "kintetsu_20260111081515.html"
_URL = "https://www.kintetsu.jp/unkou/unkou.html"
_DETAIL_URL = "https://www.kintetsu.jp/unkou/files/123456.html"
# Invented prose and summary; only the DOM shape follows the inspected page.
_DETAIL = '''<div class="title">近鉄列車運行情報</div>
<a href="#tran">詳細情報確認</a><table><tr><td><p id="tran"><br>
テスト本文：運転見合わせという語を含む案内。<br>対象区間：<b>テスト駅</b>～試験駅<br>
振替輸送：<br>テストの案内です。<script>unwanted()</script><style>.hidden{}</style>
</td></tr></table><div class="caption">除外する注意事項</div>'''
_DESCRIPTION = "テスト本文：運転見合わせという語を含む案内。\n対象区間：テスト駅～試験駅\n振替輸送：\nテストの案内です。"


def _synthetic_summary(*rows: tuple[str, str, str]) -> bytes:
    return ('''<div class="title">近鉄列車運行情報</div>
<table><thead><tr><th>路線名</th><th>状況</th><th>原因</th><th>詳細</th></tr></thead></table>
<table>''' + "".join(
        f'''<tr><td>{name}</td><td>{label}</td><td>テストの原因</td>
<td><input onclick="window.open('./files/{filename}.html')"></td></tr>'''
        for name, label, filename in rows
    ) + '</table><table><tr><td class="caption">注意事項</td></tr></table>').encode("cp932")


def _synthetic_detail_response() -> httpx.Response:
    return httpx.Response(200, content=_DETAIL.encode("cp932"))


@pytest.mark.parametrize(("fixture", "expected"), [
    (_NORMAL, {}),
    (_PARTIAL, {"kashihara": LineStatus.PARTIAL_SUSPENSION, "kyoto": LineStatus.PARTIAL_SUSPENSION}),
    ("kintetsu_20260305143142.html", {"kyoto": LineStatus.ALERT}),
    ("kintetsu_20260504000342.html", {
        "toba": LineStatus.SUSPENDED, "shima": LineStatus.PARTIAL_SUSPENSION,
        "yamada": LineStatus.PARTIAL_SUSPENSION,
    }),
    ("kintetsu_20261101.html", {"kyoto": LineStatus.SUSPENDED}),
])
def test_official_summaries(fixture: str, expected: dict[str, LineStatus]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/unkou/files/"):
            return _synthetic_detail_response()
        assert str(request.url) == _URL
        return httpx.Response(200, content=(_FIXTURES / fixture).read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KintetsuProvider(client=client)
            assert len(provider.unknown_lines) == 23
            await provider.refresh()
            assert len(provider.lines) == len({line.line_id for line in provider.lines}) == 23
            for line in provider.lines:
                key = line.line_id.rsplit(":", 1)[1]
                assert line.status is expected.get(key, LineStatus.NORMAL)
                assert line.operator.name == "近畿日本鉄道"
                assert line.line_id in LINE_CATALOG
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                assert line.updated_at is None
                if key in expected:
                    assert line.alerts[0].affected_line_ids == (line.line_id,)
                    assert line.alerts[0].description == _DESCRIPTION
                    assert line.alerts[0].source_url.startswith("https://www.kintetsu.jp/unkou/files/")
                else:
                    assert not line.alerts
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("fixture", ["kintetsu_20260601231132.html", "kintetsu_20250820134746.html"])
def test_official_unscoped_notices_are_preserved(fixture: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=(_FIXTURES / fixture).read_bytes()),
        )) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            assert len(provider.unknown_lines) == 23
            assert provider.alerts
            assert all(alert.affected_line_ids == () for alert in provider.alerts)
            assert "について" in provider.alerts[0].description
            assert not provider.delay_lines

    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "expected"), [
    ("遅れ", LineStatus.DELAYED), ("遅延", LineStatus.DELAYED),
    ("新しい表示", LineStatus.UNKNOWN),
])
def test_synthetic_status_labels(label: str, expected: LineStatus) -> None:
    # These labels are synthetic; the observed archive labels are tested above.
    html = (_FIXTURES / "kintetsu_20261101.html").read_bytes().decode("cp932")
    payload = html.replace("運転見合わせ", label).encode("cp932")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: (_synthetic_detail_response() if request.url.path.startswith("/unkou/files/")
                             else httpx.Response(200, content=payload)),
        )) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            assert provider.kyoto.status is expected
            assert provider.kyoto.source_status == label
            assert provider.kyoto.alerts[0].description == _DESCRIPTION
            assert provider.nara.status is LineStatus.NORMAL

    asyncio.run(scenario())


@pytest.mark.parametrize("change", [
    "maintenance", "missing_status", "missing_table", "missing_link", "unknown_route",
    "duplicate_row", "empty_table", "conflict", "unknown_table", "bad_encoding",
])
def test_synthetic_malformed_and_fetch_failures_preserve_snapshot(change: str) -> None:
    from bs4 import BeautifulSoup

    html = (_FIXTURES / "kintetsu_20261101.html").read_bytes().decode("cp932")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table")
    row = tables[1].select_one("tr")
    assert row is not None
    if change == "maintenance":
        html = "<html>Maintenance</html>"
    elif change == "bad_encoding":
        html = ""
    elif change == "missing_status":
        row.select("td")[1].clear()
    elif change == "missing_table":
        tables[1].decompose()
    elif change == "missing_link":
        row.select("td")[3].clear()
    elif change == "unknown_route":
        row.select("td")[0].string = "新路線"
    elif change == "duplicate_row":
        tables[1].append(BeautifulSoup(str(row), "html.parser"))
    elif change == "empty_table":
        row.decompose()
    elif change == "conflict":
        title = soup.select_one(".title")
        assert title is not None
        title.insert_after(BeautifulSoup(
            '<font>現在は１５分以上の列車の遅れはございません。</font>', "html.parser",
        ))
    elif change == "unknown_table":
        tables[0].decompose()
    if change not in ("maintenance", "bad_encoding"):
        html = str(soup)
    bad_payload = b"\x81" if change == "bad_encoding" else html.encode("cp932")
    phase = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/unkou/files/"):
            return _synthetic_detail_response()
        if phase == 2:
            return httpx.Response(503)
        return httpx.Response(200, content=(
            (_FIXTURES / _PARTIAL).read_bytes() if phase == 0 else bad_payload
        ))

    async def scenario() -> None:
        nonlocal phase
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            phase = 1
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            phase = 2
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_tracker_selection_recovery_and_failure_isolation() -> None:
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "trafficinfo.westjr.co.jp":
            return httpx.Response(503)
        if request.url.path.startswith("/unkou/files/"):
            return _synthetic_detail_response()
        return httpx.Response(200, content=(_FIXTURES / (_NORMAL if recovered else _PARTIAL)).read_bytes())

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KintetsuProvider(client=client)
            tracker = Tracker(enabled_providers=("kintetsu", "jrw"), overrides=(provider,), client=client)
            with pytest.raises(RefreshError):
                await tracker.refresh()
            assert set(tracker.refresh_errors) == {ProviderId("jrw")}
            old = tracker.kintetsu.kyoto
            assert old.status is LineStatus.PARTIAL_SUSPENSION
            assert sum(1 for _ in tracker.affected_lines) == 2
            recovered = True
            with pytest.raises(RefreshError):
                await tracker.refresh()
            assert tracker.kintetsu.kyoto.status is LineStatus.NORMAL
            assert old.status is LineStatus.PARTIAL_SUSPENSION
            assert tracker.alerts == () and tracker.affected_lines == ()
            selected = Tracker(enabled_providers=("kintetsu",), client=client)
            await selected.refresh()
            assert len(selected.lines) == 23
            assert selected.kintetsu.nishi_shigi_cable.line_id == LineId("jp:kintetsu:nishi_shigi_cable")
            assert len(selected.osaka_metro.unknown_lines) == 9

    asyncio.run(scenario())


def test_synthetic_detail_text_source_url_and_shared_request() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            return httpx.Response(200, content=_synthetic_summary(
                ("名古屋線", "遅延", "123456"), ("大阪線", "新しい表示", "123456"),
            ))
        assert str(request.url) == _DETAIL_URL
        return _synthetic_detail_response()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            assert requests == [_URL, _DETAIL_URL]
            assert provider.nagoya.status is LineStatus.DELAYED
            assert provider.osaka.status is LineStatus.UNKNOWN
            assert provider.nara.status is LineStatus.NORMAL
            for line in (provider.nagoya, provider.osaka):
                alert, = line.alerts
                assert alert.description == _DESCRIPTION
                assert alert.source_url == _DETAIL_URL
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.timing is AlertTiming.UNKNOWN
                assert line.source_url == _URL
                assert line.updated_at is None

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [
    "http", "encoding", "missing_title", "missing_body", "duplicate_body", "missing_cell", "empty_body",
])
def test_synthetic_detail_failure_preserves_complete_snapshot(failure: str) -> None:
    phase = 0
    requested_details: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _URL:
            return httpx.Response(200, content=_synthetic_summary(
                ("名古屋線", "遅延", "123456"), ("大阪線", "運転見合わせ", "654321"),
            ))
        requested_details.append(str(request.url))
        if phase == 0 or str(request.url) == _DETAIL_URL:
            return _synthetic_detail_response()
        if failure == "http":
            return httpx.Response(503)
        if failure == "encoding":
            return httpx.Response(200, content=b"\x81")
        html = _DETAIL
        if failure == "missing_title":
            html = html.replace('class="title"', 'class="changed"')
        elif failure == "missing_body":
            html = html.replace('id="tran"', 'id="changed"')
        elif failure == "duplicate_body":
            html += '<p id="tran">重複</p>'
        elif failure == "missing_cell":
            html = '<div class="title">近鉄列車運行情報</div><p id="tran">本文</p>'
        elif failure == "empty_body":
            html = '<div class="title">近鉄列車運行情報</div><table><tr><td><p id="tran"><br></td></tr></table>'
        return httpx.Response(200, content=html.encode("cp932"))

    async def scenario() -> None:
        nonlocal phase
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            phase = 1
            with pytest.raises(FetchError if failure == "http" else ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert requested_details == [_DETAIL_URL, _DETAIL_URL.replace("123456", "654321")] * 2
            phase = 0
            await provider.refresh()
            assert provider.lines is not previous

    asyncio.run(scenario())


def test_captured_live_delay_and_detail() -> None:
    summary = (_FIXTURES / "kintetsu_20261107.html").read_bytes()
    detail = (_FIXTURES / "kintetsu_detail_940571_20261107.html").read_bytes()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=summary if str(request.url) == _URL else detail),
        )) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            assert provider.nagoya.status is LineStatus.DELAYED
            alert, = provider.nagoya.alerts
            assert alert.source_url == "https://www.kintetsu.jp/unkou/files/940571.html"
            assert "遅延区間：" in alert.description
            assert "振替輸送：" in alert.description
            assert "原因:" not in alert.description and "詳細:" not in alert.description
            assert "近鉄列車運行情報について" not in alert.description
            assert provider.nagoya.updated_at is None

    asyncio.run(scenario())
