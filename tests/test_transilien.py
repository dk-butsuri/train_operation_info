"""Live Transilien JSON and explicitly synthetic recovery/failure scenarios."""

import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, UsagePermission
from train_operation_info.providers.transilien import TransilienProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_BASE = "https://www.transilien.com/api/traffic/"
_CODES = ("RER_C", "RER_D", "RER_E", "LIGNE_H", "LIGNE_J", "LIGNE_K",
          "LIGNE_L", "LIGNE_N", "LIGNE_P", "LIGNE_R", "LIGNE_U", "LIGNE_V")


def _fixture(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    if str(request.url) == _BASE + "infos":
        name = "transilien_summary.json"
    else:
        assert dict(request.url.params) == {"lang": "fr"}
        code = request.url.path.removeprefix("/api/traffic/line/")
        assert code in _CODES
        name = f"transilien_{code.lower()}.json"
    return httpx.Response(200, content=(_FIXTURES / name).read_bytes())


def _notice(**changes: str) -> dict[str, str]:
    return {
        "id": "synthetic-incident", "category": "TRAFIC", "severity": "UNKNOWN",
        "title": "Avis de circulation", "detail": "<p>Information de la ligne.</p>",
        "modifiedDate": "2026-11-03T03:00:00Z", **changes,
    }


def _payload(notices: list[dict[str, str]]) -> bytes:
    return json.dumps({"currentDisruptions": notices}).encode()


async def _with_payload(payload: bytes) -> TransilienProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/line/" in request.url.path:
            return httpx.Response(200, content=payload)
        return _fixture(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TransilienProvider(client=client)
        await provider.refresh()
        return provider


def test_official_current_notices_and_declared_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _fixture(request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TransilienProvider(client=client)
            assert len(provider.unknown_lines) == 12
            await provider.refresh()
            assert len(requests) == 13
            assert len(provider.lines) == 12
            assert len(provider.alerts) == 6
            assert all(line.operator.name == "SNCF Voyageurs" for line in provider.lines)
            assert provider.rer_d.status is LineStatus.ALERT
            assert len(provider.rer_d.alerts) == 4
            assert provider.rer_d.updated_at == datetime.fromisoformat("2026-11-03T03:07:27+00:00")
            assert "plusieurs mois" in provider.rer_d.alerts[0].description
            assert "https://maligned.transilien.com/2026/08/21/reduction-de-loffre-rer-d-24-aout/" in provider.rer_d.alerts[0].description
            # Dedicated severity is UNKNOWN even though the prose describes cancellations.
            assert all(alert.effect is AlertEffect.OTHER for alert in provider.alerts)
            assert all(alert.timing is AlertTiming.UNKNOWN for alert in provider.alerts)
            assert all(alert.language == "fr" for alert in provider.alerts)
            assert all(alert.active_from is None and alert.active_until is None for alert in provider.alerts)
            assert all(alert.affected_line_ids == (provider.rer_d.line_id,) for alert in provider.rer_d.alerts)
            # Current TRAVAUX and future engineering work cannot establish a traffic alert.
            for line in (provider.ligne_l, provider.ligne_r, provider.ligne_n):
                assert line.status is LineStatus.NORMAL and not line.alerts
                assert line.updated_at is None
            assert all(line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                       for line in provider.lines)
            assert not client.is_closed
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED

    asyncio.run(scenario())


@pytest.mark.parametrize(("severity", "status", "effect"), [
    ("SLOWED_TRAFFIC", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("HIGHLY_SLOWED_TRAFFIC", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("DISRUPTED_TRAFFIC", LineStatus.ALERT, AlertEffect.OTHER),
    ("INTERRUPTED_TRAFFIC", LineStatus.ALERT, AlertEffect.OTHER),
    ("UNKNOWN", LineStatus.ALERT, AlertEffect.OTHER),
    ("NEW_SEVERITY", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
])
def test_synthetic_severity_preserves_impact_uncertainty(
    severity: str, status: LineStatus, effect: AlertEffect,
) -> None:
    provider = asyncio.run(_with_payload(_payload([_notice(severity=severity)])))
    assert provider.rer_c.status is status
    assert provider.rer_c.alerts[0].effect is effect
    assert provider.rer_c.alerts[0].timing is AlertTiming.UNKNOWN


@pytest.mark.parametrize("description", [
    "Le trafic est interrompu demain, puis sera rétabli.",
    "L'ancien avis disait « trafic interrompu » ; cet avis est annulé.",
    "Le site est temporairement indisponible, les trains circulent normalement.",
    "L’offre est réduite pendant plusieurs mois.",
])
def test_synthetic_prose_never_classifies_effect_or_timing(description: str) -> None:
    provider = asyncio.run(_with_payload(_payload([_notice(detail=f"<p>{description}</p>")])))
    alert = provider.rer_c.alerts[0]
    assert provider.rer_c.status is LineStatus.ALERT
    assert alert.description == description
    assert alert.timing is AlertTiming.UNKNOWN and alert.effect is AlertEffect.OTHER


def test_synthetic_unknown_category_retains_text() -> None:
    provider = asyncio.run(_with_payload(_payload([_notice(category="NEW_CATEGORY")])))
    assert provider.rer_c.status is LineStatus.UNKNOWN
    assert len(provider.rer_c.alerts) == 1
    assert "NEW_CATEGORY" in (provider.rer_c.source_status or "")


def test_synthetic_excluded_works_and_future_fields_are_not_validated() -> None:
    payload = json.dumps({
        "currentDisruptions": [{"category": "TRAVAUX", "modifiedDate": False}],
        "futureDisruptions": False, "weeklyFutureDisruptions": "invalid out-of-scope",
        "monthlyFutureDisruptions": None,
    }).encode()
    provider = asyncio.run(_with_payload(payload))
    assert not provider.alerts
    assert all(line.status is LineStatus.NORMAL for line in provider.lines)


def test_synthetic_empty_current_list_clears_old_notices() -> None:
    empty = False

    def handler(request: httpx.Request) -> httpx.Response:
        if empty and "/line/" in request.url.path:
            return httpx.Response(200, json={"currentDisruptions": []})
        return _fixture(request)

    async def scenario() -> None:
        nonlocal empty
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TransilienProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            assert provider.alerts
            empty = True
            await provider.refresh()
            assert not provider.alerts
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)

    asyncio.run(scenario())


@pytest.mark.parametrize("bad_payload", [
    b"{}", b'{"currentDisruptions":null}', b'{"currentDisruptions":{}}',
    b'{"currentDisruptions":[{"category":"TRAFIC"}]}',
    _payload([_notice(title="")]),
    _payload([_notice(modifiedDate="2026-11-03T03:00:00")]),
    _payload([_notice(detail="<p></p>")]),
    _payload([_notice(), _notice()]),
])
def test_synthetic_broken_last_route_preserves_entire_previous_snapshot(bad_payload: bytes) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and request.url.path.endswith("/LIGNE_V"):
            return httpx.Response(200, content=bad_payload)
        return _fixture(request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TransilienProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("mutate", [
    lambda raw: raw.replace(b'"fetchStatus":"FULL"', b'"fetchStatus":"MISSING_CURRENT"'),
    lambda raw: raw.replace(b'"code":"RER_C"', b'"code":"RER_D"'),
    lambda raw: raw.replace(b'"id":"RER_C"', b'"id":"RER_A"'),
    lambda raw: raw.replace(b'"mode":"TRAIN"', b'"mode":"METRO"'),
])
def test_synthetic_incomplete_or_ambiguous_summary_is_not_normal(
    mutate: Callable[[bytes], bytes],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/traffic/infos"
        return httpx.Response(200, content=mutate((_FIXTURES / "transilien_summary.json").read_bytes()))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TransilienProvider(client=client)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert len(provider.unknown_lines) == 12

    asyncio.run(scenario())


def test_http_failure_does_not_return_normal() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(503),
        )) as client:
            provider = TransilienProvider(client=client)
            with pytest.raises(FetchError):
                await provider.refresh()
            assert len(provider.unknown_lines) == 12

    asyncio.run(scenario())


def test_saved_fixture_hashes_match_manifest() -> None:
    # Validate recorded evidence independently of parser expectations.
    manifest = json.loads((_FIXTURES / "transilien_manifest.json").read_text(encoding="utf-8"))
    for record in manifest:
        assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record.get(
            "fixture_sha256", record["sha256"],
        )
