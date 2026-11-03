"""Real current route rows; recovery and malformed/unknown cases are synthetic."""

import asyncio
from collections import Counter
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup, Tag
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, LINE_CATALOG, LineId, LineScope, LineStatus, ProviderId
from train_operation_info.providers.jreast import JrEastProvider
from train_operation_info.providers.jreast.provider import _AREA_ROUTES, _BINDINGS, _parse_area

_FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(area: str) -> str:
    return (_FIXTURES / f"jreast_{area}_20261102.html").read_text(encoding="utf-8")


def _response(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "traininfo.jreast.co.jp"
    area = request.url.path.rsplit("/", 1)[-1].removesuffix(".aspx")
    assert area in _AREA_ROUTES
    return httpx.Response(200, text=_fixture(area))


def _row(soup: BeautifulSoup, source_id: str) -> Tag:
    link = soup.select_one(f"a[href$='lineid={source_id}']")
    assert link is not None
    item = link.find_parent("li")
    assert isinstance(item, Tag)
    return item


def test_official_rows_and_canonical_identity() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_response)) as client:
            provider = JrEastProvider(client=client)
            assert len(provider.unknown_lines) == 86
            await provider.refresh()
            assert len(provider.lines) == len({line.line_id for line in provider.lines}) == 86
            assert Counter(line.status for line in provider.lines) == {
                LineStatus.NORMAL: 58, LineStatus.ALERT: 16, LineStatus.SUSPENDED: 6,
                LineStatus.DELAYED: 5, LineStatus.PARTIAL_SUSPENSION: 1,
            }
            assert provider.yamanote.status is LineStatus.NORMAL
            assert provider.yamanote.alerts == ()
            assert provider.yokosuka.status is LineStatus.DELAYED
            assert "東海道線内でのお客さま転落" in provider.yokosuka.alerts[0].description
            assert provider.ou.status is LineStatus.PARTIAL_SUSPENSION
            assert any(alert.effect is AlertEffect.REDUCED_SERVICE for alert in provider.ou.alerts)
            assert provider.joban.status is LineStatus.SUSPENDED
            assert "運転再開見込" in (provider.joban.source_status or "")
            assert any("１２時１０分頃" in alert.description for alert in provider.joban.alerts)
            # A reduced-service/info row in Shinetsu cannot clear Kanto's suspension.
            assert provider.koumi.status is LineStatus.SUSPENDED
            assert any(alert.effect is AlertEffect.NO_SERVICE for alert in provider.koumi.alerts)
            # Notices mentioning cancellations keep the source's notice classification.
            assert provider.yonesaka.status is LineStatus.ALERT
            assert provider.ofunato_brt.line_id != provider.ofunato.line_id
            assert provider.sotetsu_through.scope is LineScope.GROUP
            assert provider.tokyo_monorail.operator.name == "東京モノレール"
            for line in provider.lines:
                assert line.line_id in LINE_CATALOG
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                assert line.updated_at is None  # Region header is the page clock.
                assert line.source_line_names
                assert all(alert.affected_line_ids == (line.line_id,) for alert in line.alerts)
            assert "lineid=yokosukaline" in provider.yokosuka.alerts[0].source_url
            assert len(provider.alerts) == len({alert.alert_id for alert in provider.alerts}) == 49
            assert not client.is_closed

    asyncio.run(scenario())


def test_existing_ids_and_explicit_properties() -> None:
    tracker = Tracker(enabled_providers=("jreast",))
    east = tracker.jreast
    assert east.yamanote.line_id == tracker.yahoo.yamanote.line_id
    assert east.yamanote.operator is tracker.yahoo.yamanote.operator
    assert east.yamanote is not tracker.yahoo.yamanote
    assert east.hokuriku_shinkansen.line_id == tracker.jrw.hokuriku_shinkansen.line_id
    assert east.hokuriku_shinkansen is not tracker.jrw.hokuriku_shinkansen
    # Official full-route entries must not silently overwrite Yahoo section IDs.
    assert east.chuo.line_id != LineId("jp:jr_east:line_b100d0d169c8")
    assert east.ome.line_id != LineId("jp:jr_east:line_10385e063777")
    assert east.saikyo.line_id != LineId("jp:jr_east:line_0015538babb1")
    for key, (prop, _, identifier) in _BINDINGS.items():
        assert isinstance(JrEastProvider.__dict__[prop], property)
        assert getattr(east, prop) is east.get_line(identifier)
        assert key in {route for routes in _AREA_ROUTES.values() for route in routes}


def test_synthetic_recovery_clears_old_alerts_and_keeps_source_state_independent() -> None:
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        if recovered and request.url.path.endswith("kanto.aspx"):
            soup = BeautifulSoup(_fixture("kanto"), "html.parser")
            status = _row(soup, "yokosukaline").select_one(".traininfo-routes__status")
            assert status is not None
            status["class"] = "traininfo-routes__status normal"
            status.string = "平常運転"
            # Deliberately leave the previous incident prose in the row.
            return httpx.Response(200, text=str(soup))
        return _response(request)

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("jreast",), client=client)
            await tracker.refresh()
            old = tracker.jreast.yokosuka
            assert old.status is LineStatus.DELAYED
            assert tracker.yahoo.yamanote.status is LineStatus.UNKNOWN
            recovered = True
            await tracker.refresh()
            assert tracker.jreast.yokosuka.status is LineStatus.NORMAL
            assert tracker.jreast.yokosuka.alerts == ()
            assert old.status is LineStatus.DELAYED and old.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "marker"), [
    ("未知の表示", "delay"), ("遅延", "new-marker"),
    ("平常運転", "delay"), ("運転再開", "adjust"),
])
def test_synthetic_unknown_status_keeps_original(label: str, marker: str) -> None:
    soup = BeautifulSoup(_fixture("kanto"), "html.parser")
    status = _row(soup, "yokosukaline").select_one(".traininfo-routes__status")
    assert status is not None
    status["class"] = f"traininfo-routes__status {marker}"
    status.string = label
    report = next(row for row in _parse_area(str(soup), "kanto") if row.source_id == "yokosukaline")
    assert report.status is LineStatus.UNKNOWN
    assert report.label == label
    assert "お客さま転落" in report.description


def test_synthetic_unknown_shinkansen_without_incident_prose_is_not_normal() -> None:
    soup = BeautifulSoup(_fixture("shinkansen"), "html.parser")
    status = soup.select_one(".traininfo-routes__status")
    assert status is not None
    status["class"] = "traininfo-routes__status new-marker"
    report = _parse_area(str(soup), "shinkansen")[0]
    assert report.status is LineStatus.UNKNOWN
    assert report.label == "平常運転"
    assert "new-marker" in report.description


@pytest.mark.parametrize("damage", ["route", "name", "status", "description", "link", "gid", "unknown_route"])
def test_synthetic_damage_preserves_entire_previous_snapshot(damage: str) -> None:
    broken = False
    soup = BeautifulSoup(_fixture("kanto"), "html.parser")
    row = _row(soup, "yokosukaline")
    if damage == "route":
        row.decompose()
    elif damage in ("name", "status", "description"):
        selector = {"name": ".traininfo-routes__name", "status": ".traininfo-routes__status",
                    "description": ".traininfo-routes__note"}[damage]
        node = row.select_one(selector)
        assert node is not None
        node.decompose()
    else:
        link = row.select_one("a")
        assert link is not None
        link["href"] = {
            "link": "https://example.com/train_info/line.aspx?gid=1&lineid=yokosukaline",
            "gid": "/train_info/line.aspx?gid=4&lineid=yokosukaline",
            "unknown_route": "/train_info/line.aspx?gid=1&lineid=unknownline",
        }[damage]

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and request.url.path.endswith("kanto.aspx"):
            return httpx.Response(200, text=str(soup))
        return _response(request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrEastProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "transport", "markup"])
def test_later_region_failure_is_atomic(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and request.url.path.endswith("shinkansen.aspx"):
            if failure == "transport":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(503 if failure == "http" else 200, text="maintenance")
        return _response(request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrEastProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError if failure == "markup" else FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_selection_injection_and_other_provider_failure() -> None:
    async def scenario() -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.host or "")
            return _response(request) if request.url.host == "traininfo.jreast.co.jp" else httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrEastProvider(client=client)
            assert any(
                p.provider_id == provider.provider_id for p in Tracker().providers
            )
            tracker = Tracker(enabled_providers=(), overrides=(provider,))
            await tracker.refresh()
            assert tracker.jreast is provider and not requested
            tracker = Tracker(enabled_providers=("jreast",), overrides=(provider,))
            await tracker.refresh()
            assert tracker.providers == (provider,)
            assert tracker.lines == provider.lines
            assert set(requested) == {"traininfo.jreast.co.jp"}
            tracker = Tracker(enabled_providers=("jreast", "jrw"), client=client)
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("jrw")}
            assert tracker.jreast.yamanote.status is LineStatus.NORMAL

    asyncio.run(scenario())
