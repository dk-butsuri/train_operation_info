"""The live MTA subway alerts capture plus synthetic changes built from it.

mta_subway_alerts_20261103033316.pb is an unmodified official response. Synthetic
feeds are appended/encoded in the tests and named as such; see
tests/fixtures/MTA_SUBWAY.md for what each case does and does not establish.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, DataFormat, LineId, LineStatus, OperatorId,
    ProviderId, UsagePermission,
)
from train_operation_info.providers.mta_subway import MtaSubwayProvider

_FIXTURE = Path(__file__).parent / "fixtures" / "mta_subway_alerts_20261103033316.pb"
_FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts"


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


def _synthetic_entity(identifier: str, *routes: str, effect: int | None = None, stop: str | None = None) -> bytes:
    """A FeedEntity appended to the real feed; the source itself never sets effect."""
    selectors = b"".join(
        _bytes(5, _str(1, "MTASBWY") + _str(2, route) + (b"" if stop is None else _str(5, stop)))
        for route in routes
    ) if routes else _bytes(5, _str(1, "MTASBWY") + _str(5, stop or "A02"))
    alert = selectors + _bytes(10, _bytes(1, _str(1, f"Synthetic {identifier}") + _str(2, "en")))
    if effect is not None:
        alert += _varint(7 << 3) + _varint(effect)
    return _bytes(2, _str(1, identifier) + _bytes(5, alert))


def _real() -> bytes:
    return _FIXTURE.read_bytes()


def test_official_feed_keeps_unplanned_alerts_and_excludes_planned_work() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == _FEED_URL
        return httpx.Response(200, content=_real(), headers={"content-type": "application/x-protobuf"})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert "mta_subway" not in {p.provider_id for p in Tracker(client=client).providers}
            tracker = Tracker(enabled_providers=("mta_subway",), client=client)
            provider = tracker.mta_subway
            assert len(tracker.unknown_lines) == 29
            await tracker.refresh()
            assert not client.is_closed
        affected = {LineId(f"us:nyct_subway:{route}") for route in ("b", "f", "g", "q")}
        for line in provider.lines:
            assert line.operator is LINE_CATALOG[line.line_id].operator
            assert line.operator.operator_id == OperatorId("us:mta_nyct")
            assert line.provider_id == ProviderId("mta_subway")
            assert line.updated_at == datetime(2026, 11, 3, 3, 2, 19, tzinfo=timezone.utc)
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            if line.line_id in affected:
                # MTA documents effect as unused, so the kind of disruption is unknown.
                assert line.status is LineStatus.UNKNOWN
                assert line.source_status == "UNKNOWN_EFFECT (absent)"
            else:
                assert line.status is LineStatus.NORMAL and not line.alerts
        delays, skipped = sorted(provider.alerts, key=lambda alert: alert.alert_id)
        assert delays.alert_id == "lmm:alert:274643:26"
        assert delays.affected_line_ids == (provider.route_f.line_id, provider.route_g.line_id)
        assert delays.title.startswith("Coney Island-Stillwell Av-bound [F] and Church Av-bound [G] trains")
        assert skipped.alert_id == "lmm:alert:274645:29"
        assert skipped.affected_line_ids == (provider.route_b.line_id, provider.route_q.line_id)
        for alert in (delays, skipped):
            assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
            assert alert.language == "en" and "<" not in alert.title
            assert alert.active_from is None and alert.active_until is None
            assert alert.source_url == "https://www.mta.info/"
        assert provider.route_f.alerts == (delays,)
        assert not provider.active_alerts and len(provider.unclassified_alerts) == 2

    asyncio.run(scenario())


def test_official_later_capture_clears_ended_alerts() -> None:
    """Two real captures 81 minutes apart: F/G/B alerts ended, Q/3/E have current ones."""
    payload = _real()

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            earlier = provider.lines
            payload = (_FIXTURE.parent / "mta_subway_alerts_20261103045354.pb").read_bytes()
            await provider.refresh()
        for route in (provider.route_f, provider.route_g, provider.route_b):
            assert route.status is LineStatus.NORMAL and not route.alerts
        for route in (provider.route_q, provider.route_3, provider.route_e):
            assert route.status is LineStatus.UNKNOWN and len(route.alerts) == 1
        assert {alert.alert_id for alert in provider.alerts} == {
            "lmm:alert:274645:26", "lmm:alert:274654:26", "lmm:alert:274655:26",
        }
        # The alerts carry an active_period end; it is a display window, not an incident end.
        assert all(alert.active_until is None for alert in provider.alerts)
        assert provider.route_f.updated_at == datetime(2026, 11, 3, 4, 46, 35, tzinfo=timezone.utc)
        assert sum(line.status is LineStatus.UNKNOWN for line in earlier) == 4

    asyncio.run(scenario())


def test_metadata_records_terms_and_protobuf_endpoint() -> None:
    metadata = MtaSubwayProvider().metadata
    endpoint, = metadata.endpoints
    assert endpoint.url == _FEED_URL and endpoint.format is DataFormat.PROTOBUF
    assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(metadata.terms_url) == "https://www.mta.info/developers/terms-and-conditions"
    assert "non-MTA server" in metadata.usage_note


@pytest.mark.parametrize(("entity", "route", "expected"), [
    (_synthetic_entity("lmm:alert:900001", "A", effect=1), "a", LineStatus.SUSPENDED),
    (_synthetic_entity("lmm:alert:900002", "A", effect=1, stop="A02"), "a", LineStatus.ALERT),
    (_synthetic_entity("lmm:alert:900003", "6X", effect=3), "6x", LineStatus.DELAYED),
    (_synthetic_entity("lmm:alert:900004", "SI", effect=7), "si", LineStatus.ALERT),
])
def test_synthetic_effects_then_recovery_to_the_real_feed(entity: bytes, route: str, expected: LineStatus) -> None:
    payload = _real() + entity

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            disrupted = provider.get_line(LineId(f"us:nyct_subway:{route}"))
            assert disrupted is not None
            assert disrupted.status is expected and len(disrupted.alerts) == 1
            payload = _real()
            await provider.refresh()
            recovered = provider.get_line(LineId(f"us:nyct_subway:{route}"))
            assert recovered is not None
            assert recovered.status is LineStatus.NORMAL and not recovered.alerts
            assert disrupted.status is expected

    asyncio.run(scenario())


def test_synthetic_planned_work_with_unregistered_route_is_ignored() -> None:
    payload = _real() + _synthetic_entity("lmm:planned_work:900005", "NEW", effect=1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            assert len(provider.alerts) == 2

    asyncio.run(scenario())


def test_synthetic_stop_only_alert_is_unscoped() -> None:
    payload = _real() + _synthetic_entity("lmm:alert:900006", stop="A02")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            unscoped = next(a for a in provider.alerts if a.alert_id == "lmm:alert:900006")
            assert unscoped.affected_line_ids == ()

    asyncio.run(scenario())


@pytest.mark.parametrize("damage", [
    _synthetic_entity("lmm:alert:900007", "NEW"),
    _synthetic_entity("mercury:alert:900008", "A"),
    _synthetic_entity("lmm:alert:274643:26", "A"),
    b"\x12\x05\x0a",
])
def test_synthetic_invalid_feed_preserves_last_snapshot(damage: bytes) -> None:
    payload = _real()

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            payload = _real() + damage
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.route_f.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_fetch_failure_keeps_snapshot(failure: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and failure == "connection":
            raise httpx.ConnectError("synthetic connection failure", request=request)
        return httpx.Response(503) if broken else httpx.Response(200, content=_real())

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = MtaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())
