"""Official Shift_JIS excerpts and explicitly synthetic edge cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, LineId, LineStatus, ProviderId
from train_operation_info.providers.kintetsu import KintetsuProvider
from train_operation_info import Tracker

_FIXTURES = Path(__file__).parent / "fixtures"
_NORMAL = "kintetsu_20260213065943.html"
_PARTIAL = "kintetsu_20260111081515.html"


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
        assert str(request.url) == "https://www.kintetsu.jp/unkou/unkou.html"
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
                    assert "原因:" in line.alerts[0].description
                    assert "https://www.kintetsu.jp/unkou/files/" in line.alerts[0].description
                else:
                    assert not line.alerts
            if fixture == _PARTIAL:
                assert "橿原線の影響" in provider.kyoto.alerts[0].description
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
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = KintetsuProvider(client=client)
            await provider.refresh()
            assert provider.kyoto.status is expected
            assert provider.kyoto.source_status == label
            assert label in provider.kyoto.alerts[0].description
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
