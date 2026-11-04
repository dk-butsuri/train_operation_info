"""Real official MNR feed and route tables; synthetic changes are named explicitly."""

import asyncio
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, DataFormat, LineId, LineStatus,
    OperatorId, ProviderId, UsagePermission,
)
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.metro_north import MetroNorthProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_CAPTURE = _FIXTURES / "metro_north_alerts_20261104115626.pb"
_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fmnr-alerts"


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _bytes(number: int, payload: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def _str(number: int, text: str) -> bytes:
    return _bytes(number, text.encode())


def _synthetic_entity(
    route: str | None, *, identifier: str = "lmm:alert:synthetic", agency: str = "MNR",
    effect: int | None = None, stop: str | None = None, trip: bool = False,
) -> bytes:
    selector = _str(1, agency)
    if route is not None:
        selector += _bytes(4, _str(5, route)) if trip else _str(2, route)
    if stop is not None:
        selector += _str(5, stop)
    alert = _bytes(5, selector) + _bytes(10, _bytes(1, _str(1, "Synthetic notice") + _str(2, "en")))
    if effect is not None:
        alert += _varint(7 << 3) + _varint(effect)
    return _bytes(2, _str(1, identifier) + _bytes(5, alert))


def _synthetic_feed(*entities: bytes) -> bytes:
    # Minimal FULL_DATASET; no source timestamp is invented.
    return _bytes(1, _str(1, "2.0")) + b"".join(entities)


def test_official_feed_keeps_train_alert_and_excludes_planned_work() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == _URL
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=_CAPTURE.read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("metro_north",), client=client)
            assert len(tracker.unknown_lines) == 9
            provider = tracker.metro_north
            before = provider.harlem
            await tracker.refresh()
            assert not client.is_closed
        assert len(provider.lines) == 9
        assert len(provider.alerts) == 1 and tracker.alerts == provider.alerts
        alert, = provider.harlem.alerts
        assert alert.alert_id == "lmm:alert:274816:24"
        assert alert.title == "The 6:01am train from Grand Central to Southeast is operating 10-15 minutes late because of a mechanical issue."
        assert alert.affected_line_ids == (provider.harlem.line_id,)
        assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
        assert alert.language == "en" and alert.description == ""
        assert "<" not in alert.title and "<" not in alert.description
        assert alert.active_from is None and alert.active_until is None
        assert alert.source_url == "https://www.mta.info/"
        assert provider.harlem.status is LineStatus.UNKNOWN
        assert provider.harlem.source_status == "UNKNOWN_EFFECT (absent)"
        assert before.status is LineStatus.UNKNOWN and not before.alerts
        assert not tracker.delay_lines and not tracker.active_alerts
        assert tracker.unclassified_alerts == (alert,)
        for line in provider.lines:
            assert line.operator is LINE_CATALOG[line.line_id].operator
            assert line.operator.operator_id == OperatorId("us:metro_north")
            assert line.provider_id == ProviderId("metro_north")
            assert line.updated_at == datetime(2026, 11, 4, 11, 38, 39, tzinfo=timezone.utc)
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            if line.line_id != provider.harlem.line_id:
                assert line.status is LineStatus.NORMAL and not line.alerts

    asyncio.run(scenario())


def test_route_names_match_official_static_gtfs_and_status_registry() -> None:
    provider = MetroNorthProvider()
    registry = json.loads((_FIXTURES / "metro_north_status_routes.json").read_text())
    assert {r["longName"] for r in registry} == {line.name for line in provider.lines} - {"Wassaic"}
    with (_FIXTURES / "metro_north_routes.txt").open(encoding="utf-8-sig", newline="") as handle:
        assert {row["route_long_name"] for row in csv.DictReader(handle)} == {
            provider.hudson.name, provider.harlem.name, provider.new_haven.name,
            provider.new_canaan.name, provider.danbury.name, provider.waterbury.name,
        }
    assert provider.wassaic.line_id != provider.harlem.line_id
    assert {line.line_id for line in provider.lines} == {
        LineId(f"us:metro_north:{suffix}") for suffix in (
            "hudson", "harlem", "new_haven", "new_canaan", "danbury", "waterbury",
            "pascack_valley", "port_jervis", "wassaic",
        )
    }


def test_metadata_and_opt_in_without_network_access() -> None:
    provider = MetroNorthProvider()
    assert "metro_north" not in {p.provider_id for p in Tracker().providers}
    metadata = provider.metadata
    endpoint, = metadata.endpoints
    assert endpoint.url == _URL and endpoint.format is DataFormat.PROTOBUF
    assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(metadata.terms_url) == "https://www.mta.info/developers/terms-and-conditions"
    assert "non-MTA server" in metadata.usage_note


@pytest.mark.parametrize(("route", "suffix"), [
    ("1", "hudson"), ("2", "harlem"), ("3", "new_haven"), ("4", "new_canaan"),
    ("5", "danbury"), ("6", "waterbury"), ("50", "pascack_valley"),
    ("51", "port_jervis"), ("wassaic", "wassaic"), ("Wassaic", "wassaic"),
])
def test_synthetic_unplanned_route_mapping_and_recovery(route: str, suffix: str) -> None:
    payload = _synthetic_feed(_synthetic_entity(route))

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
            affected, = (line for line in provider.lines if line.alerts)
            assert affected.line_id == LineId(f"us:metro_north:{suffix}")
            assert affected.status is LineStatus.UNKNOWN
            assert affected.alerts[0].affected_line_ids == (affected.line_id,)
            assert affected.updated_at is None
            # A branch/subline is not the parent; no alert propagation.
            assert all(line.status is LineStatus.NORMAL for line in provider.lines if line is not affected)
            payload = _synthetic_feed()
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL and not line.alerts for line in provider.lines)
            assert not provider.alerts and affected.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize(("effect", "stop", "trip", "status"), [
    (1, None, False, LineStatus.SUSPENDED), (3, None, False, LineStatus.DELAYED),
    (1, "1", False, LineStatus.ALERT), (3, None, True, LineStatus.ALERT),
    (7, None, False, LineStatus.ALERT), (99, None, False, LineStatus.UNKNOWN),
])
def test_synthetic_explicit_effect_respects_selector_scope(
    effect: int, stop: str | None, trip: bool, status: LineStatus,
) -> None:
    payload = _synthetic_feed(_synthetic_entity("51", effect=effect, stop=stop, trip=trip))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
            assert provider.port_jervis.status is status
            assert provider.port_jervis.alerts[0].timing is AlertTiming.UNKNOWN
            assert all(line.status is LineStatus.NORMAL for line in provider.lines if line is not provider.port_jervis)

    asyncio.run(scenario())


def test_synthetic_stop_only_alert_preserves_unknown_scope() -> None:
    payload = _synthetic_feed(_synthetic_entity(None, stop="1", effect=1))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
        assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
        alert, = provider.alerts
        assert alert.affected_line_ids == () and alert.effect is AlertEffect.NO_SERVICE

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", [
    _synthetic_entity("NEW"), _synthetic_entity("1", agency="LI"),
    _synthetic_entity("1", identifier="undocumented:1"),
    _synthetic_entity("2", identifier="lmm:alert:274816:24"), b"\x12\x05\x0a",
])
def test_synthetic_invalid_feed_preserves_last_snapshot(damage: bytes) -> None:
    payload = _CAPTURE.read_bytes()

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
            before = provider.lines
            payload += damage
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_synthetic_planned_work_is_excluded_before_route_validation() -> None:
    payload = _synthetic_feed(_synthetic_entity("unregistered", identifier="lmm:planned_work:synthetic"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
        assert all(line.status is LineStatus.NORMAL and not line.alerts for line in provider.lines)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_fetch_failure_preserves_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and failure == "connection":
            raise httpx.ConnectError("synthetic failure", request=request)
        return httpx.Response(503) if broken else httpx.Response(200, content=_CAPTURE.read_bytes())

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = MetroNorthProvider(client=client)
            await provider.refresh()
            before = provider.lines
            broken = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_saved_fixtures_match_manifest() -> None:
    records = json.loads((_FIXTURES / "metro_north_manifest.json").read_text())
    for record in records:
        if record["fixture"] is not None:
            assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record["fixture_sha256"]
