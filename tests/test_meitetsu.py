"""Official Meitetsu captures; time/transition/broken-markup cases are synthetic."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.meitetsu import MeitetsuProvider
from train_operation_info.providers.meitetsu.provider import _parse
from train_operation_info.snapshots import SnapshotReplayTransport

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://top.meitetsu.co.jp/em/"
_TIME = datetime.fromisoformat("2026-11-02T03:00:00+00:00")


def _html(name: str = "normal") -> bytes:
    return (_FIXTURES / f"meitetsu_{name}.html").read_bytes()


class _ClockedProvider(MeitetsuProvider):
    def _now(self) -> datetime:
        return _TIME


def test_real_recent_capture_merges_sections_and_retains_mixed_category() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_html("20260908095207")),
        )) as client:
            tracker = Tracker(enabled_providers=("meitetsu",), client=client)
            provider = tracker.meitetsu
            assert len(provider.lines) == 16 and len(provider.unknown_lines) == 16
            await tracker.refresh()
            assert len([l for l in provider.lines if l.status is LineStatus.SUSPENDED]) == 10
            assert len([l for l in provider.lines if l.status is LineStatus.ALERT]) == 4
            assert provider.gamagori.status is provider.takehana_hashima.status is LineStatus.NORMAL
            assert provider.nagoya_main.status is provider.inuyama.status is LineStatus.SUSPENDED
            assert provider.nishio.status is provider.kakamigahara.status is LineStatus.ALERT
            assert not tracker.delay_lines and not tracker.unknown_lines
            assert len(provider.alerts) == 2
            suspension = next(a for a in provider.alerts if a.effect is AlertEffect.NO_SERVICE)
            assert "豊明駅～新木曽川駅間" in suspension.description
            assert "まもなく運転再開" in suspension.description
            assert provider.inuyama.line_id in suspension.affected_line_ids
            assert "18時31分" in provider.inuyama.alerts[1].description
            for line in provider.lines:
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert all(a.timing is AlertTiming.UNKNOWN for a in provider.alerts)
            assert all(a.active_from is None and a.active_until is None for a in provider.alerts)
            assert not tracker.active_alerts
            assert not client.is_closed
    asyncio.run(scenario())


def test_real_single_line_suspension_does_not_assign_alternative_transport_routes() -> None:
    provider = MeitetsuProvider()
    lines = _parse(_html("20260208081057"), provider.lines, _TIME)
    hiromi = next(line for line in lines if line.line_id == provider.hiromi.line_id)
    assert hiromi.status is LineStatus.SUSPENDED
    assert len(hiromi.alerts) == 2
    assert "倒竹" in hiromi.alerts[0].description
    assert {a.effect for a in hiromi.alerts} == {AlertEffect.NO_SERVICE, AlertEffect.OTHER}
    assert all(line.status is LineStatus.NORMAL for line in lines if line is not hiromi)
    assert all(a.affected_line_ids == (hiromi.line_id,) for a in hiromi.alerts)


@pytest.mark.parametrize("capture", ["20230815094730", "20220918035311", "20240831065722"])
def test_real_free_prose_preserves_predictions_without_inventing_targets(capture: str) -> None:
    provider = MeitetsuProvider()
    lines = _parse(_html(capture), provider.lines, _TIME)
    alerts = {a.alert_id: a for line in lines for a in line.alerts}.values()
    free = [a for a in alerts if not a.affected_line_ids]
    assert free and all(a.effect is AlertEffect.OTHER for a in free)
    assert all(a.timing is AlertTiming.UNKNOWN for a in free)
    if capture == "20230815094730":
        assert all(line.status is LineStatus.ALERT for line in lines)
        assert "順次運転を再開" in free[0].description
        assert "８月１６日" in free[0].description
    elif capture == "20240831065722":
        # Gamagori occurs only in prediction prose, not in a structured target list.
        assert next(l for l in lines if l.line_id == provider.gamagori.line_id).status is LineStatus.UNKNOWN
        assert next(l for l in lines if l.line_id == provider.nagoya_main.line_id).status is LineStatus.SUSPENDED
    else:
        # The incident reason mentions Inuyama; the route list also names others.
        assert next(l for l in lines if l.line_id == provider.nagoya_main.line_id).status is LineStatus.ALERT
        assert next(l for l in lines if l.line_id == provider.seto.line_id).status is LineStatus.UNKNOWN


def test_normal_capture_clears_all_previous_alerts_and_reuses_canonical_ids() -> None:
    html = _html("20260908095207")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = _ClockedProvider(client=client)
            tracker = Tracker(enabled_providers=("meitetsu",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.nagoya_main
            for name in ("20230816075632", "normal"):
                html = _html(name)
                await tracker.refresh()
                assert all(l.status is LineStatus.NORMAL for l in tracker.lines)
                assert not tracker.alerts and not tracker.affected_lines and not tracker.unknown_lines
                assert provider.nagoya_main.source_status == "15分以上の列車の遅れはございません。"
                for line in tracker.lines:
                    yahoo = tracker.yahoo.get_line(line.line_id)
                    assert yahoo is not None and yahoo is not line and yahoo.operator == line.operator
                    assert yahoo.status is LineStatus.UNKNOWN
            assert previous.status is LineStatus.SUSPENDED and previous.alerts
            assert provider.tokoname_airport.source_line_names == ("常滑線", "空港線")
            assert provider.nagoya_main.line_id == LineId("jp:meitetsu:line_4a34e1bd4cf5")
    asyncio.run(scenario())


@pytest.mark.parametrize(("local", "expected"), [
    ("00:30:59", LineStatus.NORMAL), ("00:31:00", LineStatus.UNKNOWN),
    ("01:00:00", LineStatus.UNKNOWN), ("04:59:59", LineStatus.UNKNOWN),
    ("05:00:00", LineStatus.NORMAL), ("23:59:59", LineStatus.NORMAL),
])
def test_synthetic_clock_reproduces_official_normal_page_service_window(local: str, expected: LineStatus) -> None:
    at = datetime.fromisoformat(f"2026-11-02T{local}+09:00")
    lines = _parse(_html(), MeitetsuProvider().lines, at)
    assert all(line.status is expected and line.updated_at is None and not line.alerts for line in lines)
    if expected is LineStatus.UNKNOWN:
        assert all("提供時間" in (line.source_status or "") for line in lines)


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "missing_heading", "wrong_heading", "missing_title",
    "missing_detail", "missing_field", "duplicate_field", "empty_list", "empty_item",
    "missing_section", "missing_class", "conflicting_class", "empty_panel", "empty_free",
])
def test_synthetic_malformed_html_preserves_last_snapshot(mutation: str) -> None:
    soup = BeautifulSoup(_html("20260208081057"), "html.parser")
    panel = soup.select_one(".layEm")
    block = soup.select_one(".emInfo.emLv01")
    assert panel is not None and block is not None
    selector = {
        "missing_heading": "h1.EM", "missing_title": ".emInfoTitle h2",
        "missing_detail": ".emInfoDetail", "missing_field": "tr",
    }.get(mutation)
    if selector is not None:
        tag = soup.select_one(selector)
        assert tag is not None
        tag.decompose()
    elif mutation == "missing_panel":
        panel.decompose()
    elif mutation == "duplicate_panel":
        panel.insert_after(BeautifulSoup(str(panel), "html.parser"))
    elif mutation == "wrong_heading":
        heading = soup.select_one("h1.EM")
        assert heading is not None
        heading.string = "Synthetic wrong page"
    elif mutation == "duplicate_field":
        row = block.select_one("tr")
        assert row is not None
        row.insert_after(BeautifulSoup(str(row), "html.parser"))
    elif mutation in ("empty_list", "empty_item", "missing_section"):
        tag = block.select_one("ul.emListCmn" if mutation == "empty_list" else "li")
        assert tag is not None
        tag.clear()
        if mutation == "missing_section":
            tag.string = "広見線"
    elif mutation == "missing_class":
        block["class"] = "emInfo"
    elif mutation == "conflicting_class":
        block["class"] = "emInfo emLv01 emLv02"
    elif mutation == "empty_panel":
        panel.clear()
    else:
        panel.append(soup.new_tag("div", attrs={"class": "wrapFree"}))
    html = _html("20260208081057")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = _ClockedProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = str(soup).encode("utf-8")
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous and provider.hiromi.alerts
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["unknown_class", "unknown_title", "unknown_route", "mixed_normal"])
def test_synthetic_unrecognized_values_are_unknown_and_retain_text(mutation: str) -> None:
    soup = BeautifulSoup(_html("20260208081057"), "html.parser")
    blocks = soup.select(".emInfo")
    block = blocks[0]
    for other in blocks[1:]:
        other.decompose()
    if mutation == "unknown_class":
        block["class"] = "emInfo emLv99"
    elif mutation == "unknown_title":
        title = block.select_one("h2")
        assert title is not None
        title.string = "合成テスト：新しい状態"
    elif mutation == "unknown_route":
        item = block.select_one("li")
        assert item is not None
        item.string = "合成新線 A駅～B駅間"
    else:
        panel = soup.select_one(".layEm")
        normal = BeautifulSoup(_html(), "html.parser").select_one("#descriptionText")
        assert panel is not None and normal is not None
        panel.append(normal)
    provider = MeitetsuProvider()
    lines = _parse(str(soup).encode("utf-8"), provider.lines, _TIME)
    assert all(l.status is LineStatus.UNKNOWN for l in lines if l.line_id != provider.hiromi.line_id)
    assert all(l.alerts for l in lines if mutation != "mixed_normal")
    assert any("送電設備" in a.description for l in lines for a in l.alerts)


@pytest.mark.parametrize("failure", ["http", "connection", "soft_404"])
def test_selection_injection_and_failure_isolation(failure: str) -> None:
    requests: list[str] = []
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            if broken:
                if failure == "connection":
                    raise httpx.ConnectError("synthetic failure", request=request)
                if failure == "soft_404":
                    return httpx.Response(200, text="<h1>404 Page Not Found</h1>")
                return httpx.Response(503)
            return httpx.Response(200, content=_html("20260208081057"))
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _ClockedProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("meitetsu", "hankyu"), client=client, overrides=(provider,))
            assert tracker.meitetsu is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("meitetsu")}
            expected = ParseError if failure == "soft_404" else FetchError
            assert isinstance(captured.value.errors[ProviderId("meitetsu")], expected)
            assert provider.lines is previous and provider.hiromi.alerts
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
    asyncio.run(scenario())


def test_default_registration_and_reviewed_metadata() -> None:
    tracker = Tracker()
    provider = tracker.meitetsu
    assert provider in tracker.providers
    assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(provider.metadata.terms_url) == "https://www.meitetsu.co.jp/site_policy/index.html"
    assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
    assert provider.metadata.endpoints[0].url == _URL


def test_synthetic_http_redirect_is_recorded_under_original_endpoint_and_replayed(tmp_path: Path) -> None:
    redirected = "https://top.meitetsu.co.jp/em/ryokaku/format3.html"
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            return httpx.Response(302, headers={"location": redirected})
        assert str(request.url) == redirected
        return httpx.Response(200, content=_html("20260908095207"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            provider = MeitetsuProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            original = provider.lines
        assert requests == [_URL, redirected]
        capture, = (tmp_path / "meitetsu").glob("[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture)
        assert transport.capture.responses[0].url == _URL
        async with httpx.AsyncClient(transport=transport) as client:
            replay = MeitetsuProvider(client=client)
            await replay.refresh()
            assert replay.lines == original
    asyncio.run(scenario())


def test_synthetic_partly_unknown_target_list_keeps_both_alert_scopes() -> None:
    soup = BeautifulSoup(_html("20260208081057"), "html.parser")
    blocks = soup.select(".emInfo")
    for block in blocks[1:]:
        block.decompose()
    targets = blocks[0].select_one("ul.emListCmn")
    assert targets is not None
    item = soup.new_tag("li")
    item.string = "合成新線 A駅～B駅間"
    targets.append(item)
    html = str(soup).encode("utf-8")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = _ClockedProvider(client=client)
            await provider.refresh()
            assert provider.hiromi.status is LineStatus.SUSPENDED
            assert provider.nagoya_main.status is LineStatus.UNKNOWN
            assert len(provider.alerts) == 2
            scoped = next(a for a in provider.alerts if a.affected_line_ids)
            unscoped = next(a for a in provider.alerts if not a.affected_line_ids)
            assert scoped.alert_id != unscoped.alert_id
            assert scoped.affected_line_ids == (provider.hiromi.line_id,)
            assert unscoped.affected_line_ids == ()
            assert scoped.description == unscoped.description
            assert all(a.effect is AlertEffect.NO_SERVICE for a in provider.alerts)
    asyncio.run(scenario())
