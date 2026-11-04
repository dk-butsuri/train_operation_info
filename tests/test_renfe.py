"""Real Renfe capture and explicitly synthetic protocol/recovery scenarios."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, LineId, LineScope, LineStatus,
    UsagePermission,
)
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.renfe import RenfeProvider

_FIXTURE = Path(__file__).parent / "fixtures" / "renfe_alerts_20261104.json"
_URL = "https://gtfsrt.renfe.com/alerts.json"


def _entity(
    identifier: str = "synthetic", *, route: str = "unresolved-route",
    text: str = "Synthetic notice", effect: str | None = None,
) -> dict[str, object]:
    alert: dict[str, object] = {
        "informedEntity": [{"routeId": route}],
        "descriptionText": {"translation": [{"language": "es", "text": text}]},
        "activePeriod": [{"start": "1791356520", "end": "1791442920"}],
    }
    if effect is not None:
        alert["effect"] = effect
    return {"id": identifier, "alert": alert}


def _feed(*entities: dict[str, object]) -> bytes:
    return json.dumps({
        "header": {"gtfsRealtimeVersion": "2.0", "timestamp": "1791358372"},
        "entity": entities,
    }, ensure_ascii=False).encode()


def test_real_capture_preserves_all_notices_scopes_and_source_timestamp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url) == _URL
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=_FIXTURE.read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("renfe",), client=client)
            assert tracker.renfe.cercanias.status is LineStatus.UNKNOWN
            await tracker.refresh()
            assert not client.is_closed
        line = tracker.renfe.cercanias
        assert line.scope is LineScope.GROUP and line.status is LineStatus.UNKNOWN
        assert line.line_id == LineId("es:renfe:cercanias")
        assert line.operator is LINE_CATALOG[line.line_id].operator
        assert line.updated_at == datetime(2026, 10, 7, 7, 32, 52, tzinfo=timezone.utc)
        assert line.fetched_at is not None and line.fetched_at > line.updated_at
        assert len(line.alerts) == len(tracker.alerts) == 69
        repeated = [a for a in line.alerts if a.title == "AVISO_518187"]
        assert len(repeated) == 2 and repeated[0].alert_id != repeated[1].alert_id
        assert repeated[0].description == repeated[1].description
        for alert in line.alerts:
            assert alert.description and alert.language == "es"
            assert alert.effect is AlertEffect.UNKNOWN
            assert alert.timing is AlertTiming.UNKNOWN and alert.affected_line_ids == ()
            assert alert.active_from is None and alert.active_until is None
        assert not tracker.active_alerts

    asyncio.run(scenario())


@pytest.mark.parametrize(("effect", "expected"), [
    (None, AlertEffect.UNKNOWN), ("UNKNOWN_EFFECT", AlertEffect.UNKNOWN),
    ("FUTURE_EFFECT", AlertEffect.UNKNOWN), ("NO_SERVICE", AlertEffect.NO_SERVICE),
    ("REDUCED_SERVICE", AlertEffect.REDUCED_SERVICE),
    ("SIGNIFICANT_DELAYS", AlertEffect.DELAYS), ("NO_EFFECT", AlertEffect.OTHER),
])
def test_synthetic_effects_do_not_classify_the_whole_network(
    effect: str | None, expected: AlertEffect,
) -> None:
    payload = _feed(_entity(text="No hay retrasos. Servicio restablecido mañana.", effect=effect))

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            earlier = provider.cercanias
            alert, = earlier.alerts
            assert earlier.status is LineStatus.UNKNOWN and alert.effect is expected
            assert alert.timing is AlertTiming.UNKNOWN and alert.affected_line_ids == ()
            assert alert.active_from is None and alert.active_until is None
            payload = _feed()
            await provider.refresh()
            assert provider.cercanias.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.cercanias.alerts
            assert earlier.alerts == (alert,)  # Old snapshots remain immutable.

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    b"{}", b"not JSON",
    b'{"header":{"gtfsRealtimeVersion":"3.0","timestamp":"1791358372"}}',
    b'{"header":{"gtfsRealtimeVersion":"2.0","timestamp":1791358372}}',
    b'{"header":{"gtfsRealtimeVersion":"2.0","timestamp":"999999999999999999999"}}',
    b'{"header":{"gtfsRealtimeVersion":"2.0","timestamp":"1791358372","incrementality":"DIFFERENTIAL"}}',
    _feed({"id": "bad", "isDeleted": True, "alert": {}}),
    _feed({"id": "bad"}),
    _feed({"id": "bad", "alert": {"informedEntity": []}}),
    _feed({"id": "bad", "alert": {"informedEntity": [{"routeId": 42}]}}),
    _feed(_entity(text="")), _feed(_entity(identifier="  ")),
    _feed(_entity(), _entity()),
    _feed({"id": "bad", "alert": {"informedEntity": [{}], "descriptionText": {
        "translation": [{"language": "en", "text": "English only"}],
    }}}),
])
def test_synthetic_invalid_feed_keeps_previous_snapshot(payload: bytes) -> None:
    body = _feed(_entity())

    async def scenario() -> None:
        nonlocal body
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body),
        )) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            before = provider.lines
            body = payload
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_synthetic_repeated_source_id_uses_stable_selector_identity() -> None:
    payload = _feed(_entity(route="first"), _entity(route="second"))

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            identifiers = {a.alert_id for a in provider.alerts}
            assert len(identifiers) == 2
            payload = _feed(_entity(route="second", text="Changed text"), _entity(route="first"))
            await provider.refresh()
            assert {a.alert_id for a in provider.alerts} == identifiers

    asyncio.run(scenario())


def test_es_labels_are_preserved_without_guessing_the_actual_language() -> None:
    payload = _feed({"id": "synthetic", "alert": {
        "informedEntity": [{"stopId": "unresolved-stop"}],
        "descriptionText": {"translation": [
            {"language": "es", "text": " Primer texto. "},
            {"language": "es", "text": "Segon text."},
            {"language": "es", "text": "\r\n\r\n"},
            {"language": "en", "text": "English text."},
        ]},
    }})

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            alert, = provider.alerts
            assert alert.description == " Primer texto. \n\nSegon text."
            assert alert.language == "es" and alert.affected_line_ids == ()
            assert provider.cercanias.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


def test_protojson_omitted_repeated_field_means_empty_full_dataset() -> None:
    payload = b'{"header":{"gtfsRealtimeVersion":"2.0","timestamp":"1791358372"}}'

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload),
        )) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            assert provider.cercanias.status is LineStatus.NORMAL

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [403, 429, 503])
def test_refusal_is_not_retried_and_keeps_snapshot(status: int) -> None:
    calls: list[httpx.Request] = []
    failed = False

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status if failed else 200, content=_feed())

    async def scenario() -> None:
        nonlocal failed
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RenfeProvider(client=client)
            await provider.refresh()
            before = provider.lines
            failed = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is before and len(calls) == 2

    asyncio.run(scenario())


def test_metadata_and_default_selection() -> None:
    provider = RenfeProvider()
    assert provider.metadata.usage_permission is UsagePermission.COMMERCIAL_ALLOWED
    assert provider.metadata.statuses == frozenset({LineStatus.NORMAL})
    assert "Renfe Operadora" in provider.metadata.usage_note
    assert "renfe" in {p.provider_id for p in Tracker().providers}
    tracker = Tracker(enabled_providers=("renfe",), overrides=(provider,))
    assert tracker.renfe is provider and tracker.providers == (provider,)
