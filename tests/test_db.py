"""Live abnormal DB fixtures; clearing/expiry/malformed/pagination cases are synthetic."""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import cast

import httpx
from pydantic import JsonValue
import pytest

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineScope, LineStatus
from train_operation_info.providers.db import DbProvider
from train_operation_info.snapshots import SnapshotReplayTransport, _REPLAY_TIME

_FIXTURES = Path(__file__).parent / "fixtures"
_PAGE = (_FIXTURES / "db_page.html").read_bytes()
_LISTING = (_FIXTURES / "db_listing.json").read_bytes()
_BERLIN = "493b1167-9762-49df-a8f3-35b7dabe487e"
_CAPTURE_TIME = datetime.fromisoformat("2026-11-03T03:40:00+00:00")
_MESSAGES = {
    _BERLIN: "db_message_berlin.json",
    "89ae83a0-740d-3e50-92d6-184c6d472c71": "db_message_berlin.json",
    "15bee9d8-282e-370b-8a97-682ab0f3f37a": "db_message_wuppertal.json",
    "c1d91fe2-8cac-4287-bf5c-2d391039b910": "db_message_wuppertal.json",
}


def _response(request: httpx.Request, listing: bytes = _LISTING) -> httpx.Response:
    assert request.url.host == "verkehrslage.bahnhof.de"
    if request.url.path == "/de/region/DB_Fernverkehr":
        return httpx.Response(200, content=_PAGE, extensions={_REPLAY_TIME: _CAPTURE_TIME})
    assert request.headers["x-api-key"] == "fixture-public-key"
    if request.url.path == "/api/views/disruptions":
        assert request.url.params["channels"] == "AwarenessBlitzbox,TrafficReport"
        assert request.url.params["organisationalUnitNames"] == "DB_Fernverkehr"
        assert request.url.params["limit"] == "100"
        for key in ("from", "to"):
            assert datetime.fromisoformat(request.url.params[key]).utcoffset() is not None
        return httpx.Response(200, content=listing, extensions={_REPLAY_TIME: _CAPTURE_TIME})
    assert request.url.path == "/api/views/message"
    assert request.url.params["locale"] == "DE"
    return httpx.Response(
        200, content=(_FIXTURES / _MESSAGES[request.url.params["id"]]).read_bytes(),
        extensions={_REPLAY_TIME: _CAPTURE_TIME},
    )


def test_live_abnormal_reports_preserve_unknown_scope_and_details() -> None:
    calls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return _response(request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = DbProvider(client=client)
            await provider.refresh()
            assert len(provider.lines) == 1
            line = provider.fernverkehr
            assert str(line.line_id) == "de:db_fernverkehr:network"
            assert line.scope is LineScope.GROUP and line.status is LineStatus.UNKNOWN
            assert len(provider.alerts) == 4 and len(provider.unclassified_alerts) == 4
            assert not provider.affected_lines and not provider.delay_lines
            assert line.updated_at is None
            assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
            assert "IMPAIRMENT" in (line.source_status or "")
            for alert in provider.alerts:
                assert alert.effect is AlertEffect.OTHER
                assert alert.timing is AlertTiming.UNKNOWN and alert.affected_line_ids == ()
                assert alert.language == "de"
                assert alert.active_from is None and alert.active_until is None
                assert "<" not in alert.description
            berlin = next(a for a in provider.alerts if a.alert_id == "db:" + _BERLIN)
            assert berlin.title == "Beeinträchtigungen zwischen Berlin und Hannover"
            assert "bis zu 15 Minuten" in berlin.description
            assert "Zugausfällen" in berlin.description
            assert len(calls) == 6  # HTML, complete listing, four detail texts.
            assert not client.is_closed

    asyncio.run(scenario())


def test_synthetic_empty_scoped_listing_clears_reports() -> None:
    listing = _LISTING

    async def scenario() -> None:
        nonlocal listing
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, listing),
        )) as client:
            provider = DbProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.fernverkehr
            listing = b'{"disruptionCommunications":[],"offset":0,"limit":100,"total":0}'
            await provider.refresh()
            assert provider.fernverkehr.status is LineStatus.NORMAL
            assert provider.alerts == ()
            assert len(previous.alerts) == 4 and previous.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "config", "wrong_origin", "duplicate_key", "missing_cause", "wrong_type",
    "wrong_offset", "zero_total", "wrong_organisation", "wrong_channel", "detail_failure",
])
def test_synthetic_failures_keep_previous_snapshot(mutation: str) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not broken:
            return _response(request)
        if request.url.path == "/de/region/DB_Fernverkehr":
            page = _PAGE
            if mutation == "config":
                page = b"<html>Maintenance</html>"
            elif mutation == "wrong_origin":
                page = page.replace(b'risApiUrl:"https://verkehrslage.bahnhof.de"', b'risApiUrl:"https://example.org"')
            elif mutation == "duplicate_key":
                page = page.replace(b'risApiKey:', b'risApiKey:"other",risApiKey:')
            return httpx.Response(200, content=page)
        if request.url.path == "/api/views/disruptions":
            listing = _LISTING
            replacements = {
                "missing_cause": (b'"cause":', b'"unknown_cause":'),
                "wrong_type": (b'"total": 72', b'"total": "72"'),
                "wrong_offset": (b'"offset": 0', b'"offset": 100'),
                "zero_total": (b'"total": 72', b'"total": 0'),
                "wrong_organisation": (b'"DB_Fernverkehr"', b'"DB_Regio_Bayern"'),
                "wrong_channel": (b'"TrafficReport"', b'"OtherChannel"'),
            }
            if mutation in replacements:
                before, after = replacements[mutation]
                listing = listing.replace(before, after)
            return httpx.Response(200, content=listing)
        return httpx.Response(503) if mutation == "detail_failure" else _response(request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = DbProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError if mutation == "detail_failure" else ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def _entry(identifier: str, *, cause: str = "CONSTRUCTION") -> dict[str, JsonValue]:
    return {
        "disruptionCommunicationID": identifier,
        "consumerHints": {
            "channels": ["TrafficReport"],
            "organisationalUnits": [{"name": "DB_Fernverkehr"}],
        },
        "disruption": {"cause": cause}, "effect": "UNKNOWN_FUTURE_EFFECT",
    }


@pytest.mark.parametrize("mode", ["complete", "changed_total", "duplicate", "bad_last_page"])
def test_synthetic_pagination_completes_before_commit(mode: str) -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/views/disruptions":
            return _response(request)
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        total = 102 if mode == "changed_total" and offset == 100 else 101
        if offset == 0:
            entries: list[JsonValue] = [_entry(str(i)) for i in range(100)]
        else:
            identifier = "0" if mode == "duplicate" else _BERLIN
            entries = [_entry(identifier, cause="UNKNOWN_FUTURE_CAUSE")]
        payload: dict[str, JsonValue] = {
            "disruptionCommunications": entries, "offset": offset, "limit": 100, "total": total,
        }
        if mode == "bad_last_page" and offset:
            del payload["disruptionCommunications"]
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = DbProvider(client=client)
            previous = provider.lines
            if mode == "complete":
                await provider.refresh()
                assert len(provider.alerts) == 1
                assert provider.fernverkehr.status is LineStatus.UNKNOWN
                assert provider.alerts[0].effect is AlertEffect.OTHER
            else:
                with pytest.raises(ParseError):
                    await provider.refresh()
                assert provider.lines is previous
            assert offsets == [0, 100]

    asyncio.run(scenario())


def test_synthetic_expiry() -> None:
    payload = cast("dict[str, JsonValue]", json.loads(_LISTING))
    expired = _entry("expired", cause="OTHER_CAUSE")
    expired["end"] = "2000-01-01T00:00:00Z"
    payload["disruptionCommunications"] = [expired]
    payload["total"] = 1
    listing = json.dumps(payload).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, listing),
        )) as client:
            provider = DbProvider(client=client)
            await provider.refresh()
            assert provider.alerts == () and provider.fernverkehr.status is LineStatus.NORMAL

    asyncio.run(scenario())


@pytest.mark.parametrize("relation", ["expired_parent", "missing_parent", "standalone", "valid_parent"])
def test_synthetic_parent_expiry_matches_official_child_filter(relation: str) -> None:
    child = _entry(_BERLIN, cause="OTHER_CAUSE")
    entries: list[JsonValue] = [child]
    if relation != "standalone":
        child["parent"] = "parent"
    if relation in ("expired_parent", "valid_parent"):
        parent = _entry("parent")  # Construction output is excluded; its envelope still gates the child.
        if relation == "expired_parent":
            parent["end"] = "2026-11-03T03:39:59Z"
        entries.append(parent)
    payload: dict[str, JsonValue] = {
        "disruptionCommunications": entries, "offset": 0, "limit": 100, "total": len(entries),
    }
    listing = json.dumps(payload).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, listing),
        )) as client:
            provider = DbProvider(client=client)
            await provider.refresh()
            assert len(provider.alerts) == (1 if relation in ("standalone", "valid_parent") else 0)
            assert provider.fernverkehr.fetched_at == _CAPTURE_TIME

    asyncio.run(scenario())


def test_synthetic_excluded_construction_contents_are_not_validated() -> None:
    payload: dict[str, JsonValue] = {
        "disruptionCommunications": [{
            "disruptionCommunicationID": "construction",
            "disruption": {"cause": "CONSTRUCTION"},
            "effect": None, "consumerHints": "outside scoped interpretation",
        }],
        "offset": 0, "limit": 100, "total": 1,
    }
    listing = json.dumps(payload).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, listing),
        )) as client:
            provider = DbProvider(client=client)
            await provider.refresh()
            assert provider.alerts == () and provider.fernverkehr.status is LineStatus.NORMAL

    asyncio.run(scenario())


def test_synthetic_replay_keeps_day_and_expiry_clock_when_fetch_crosses_midnight(tmp_path: Path) -> None:
    started = datetime.fromisoformat("2026-11-03T22:59:59+00:00")
    finished = started + timedelta(seconds=2)  # Next date in Europe/Berlin.
    entry = _entry(_BERLIN, cause="OTHER_CAUSE")
    entry["end"] = (started + timedelta(seconds=1)).isoformat()
    listing = json.dumps({
        "disruptionCommunications": [entry], "offset": 0, "limit": 100, "total": 1,
    }).encode()

    class CrossingMidnight(DbProvider):
        _clock_calls = 0

        def _now(self) -> datetime:
            self._clock_calls += 1
            return started if self._clock_calls == 1 else finished

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, listing),
        )) as client:
            provider = CrossingMidnight(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            original = provider.lines
            assert provider.fernverkehr.fetched_at == started
            assert len(provider.alerts) == 1
        capture_path, = tmp_path.glob("db/[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture_path)
        assert transport.capture.captured_at == started
        async with httpx.AsyncClient(transport=transport) as client:
            replay = DbProvider(client=client)
            await replay.refresh()
            assert replay.lines == original

    asyncio.run(scenario())
