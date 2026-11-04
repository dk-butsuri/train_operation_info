"""Live TfL evidence plus explicitly synthetic schema/recovery/failure cases."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LINE_CATALOG, LineId, LineScope, LineStatus
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.tfl import TflProvider
from train_operation_info.providers.tfl.provider import _parse

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line,tram/Status"
_NOW = datetime(2026, 11, 4, 13, tzinfo=timezone.utc)


def _synthetic_status(code: int = 10, label: str = "Good Service") -> dict[str, object]:
    return {"statusSeverity": code, "statusSeverityDescription": label, "validityPeriods": []}


def _synthetic() -> list[dict[str, object]]:
    # Public line-set shape; no actual incident prose is copied into synthetic data.
    ids = (
        ("bakerloo", "tube"), ("central", "tube"), ("circle", "tube"), ("district", "tube"),
        ("dlr", "dlr"), ("elizabeth", "elizabeth-line"), ("hammersmith-city", "tube"),
        ("jubilee", "tube"), ("liberty", "overground"), ("lioness", "overground"),
        ("metropolitan", "tube"), ("mildmay", "overground"), ("northern", "tube"),
        ("piccadilly", "tube"), ("suffragette", "overground"), ("tram", "tram"),
        ("victoria", "tube"), ("waterloo-city", "tube"), ("weaver", "overground"),
        ("windrush", "overground"),
    )
    return [{"id": key, "name": key, "modeName": mode, "lineStatuses": [_synthetic_status()]}
            for key, mode in ids]


def _body(data: object) -> bytes:
    return json.dumps(data).encode()


def test_real_current_statuses_and_scope() -> None:
    body = (_FIXTURES / "tfl_live_20261104.json").read_bytes()

    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) == _URL and not request.url.params
            assert request.headers["user-agent"] == USER_AGENT
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TflProvider(client=client)
            await provider.refresh()
            assert len(requests) == 1 and len(provider.lines) == 20
            assert provider.bakerloo.status is LineStatus.PARTIAL_SUSPENSION
            assert provider.lioness.status is LineStatus.PARTIAL_SUSPENSION
            assert provider.central.status is provider.piccadilly.status is LineStatus.DELAYED
            assert provider.circle.status is provider.elizabeth.status is LineStatus.NORMAL
            assert {a.effect for a in provider.bakerloo.alerts} == {
                AlertEffect.DELAYS, AlertEffect.REDUCED_SERVICE,
            }
            assert len(provider.central.alerts) == 2
            assert provider.bakerloo.active_alerts == provider.bakerloo.alerts
            assert provider.suffragette.status is provider.tram.status is LineStatus.PARTIAL_SUSPENSION
            assert provider.suffragette.alerts[0].timing is AlertTiming.UNKNOWN
            assert provider.suffragette.alerts[0].active_from is not None
            assert not provider.suffragette.active_alerts
            assert provider.dlr.scope is provider.tram.scope is LineScope.GROUP
            assert provider.bakerloo.scope is provider.lioness.scope is LineScope.LINE
            assert provider.bakerloo.operator.name == "London Underground Limited"
            assert provider.lioness.operator.name == "First Rail London Limited"
            assert provider.elizabeth.operator.name == "GTS Rail Operations Limited"
            assert provider.dlr.operator.name == "KeolisAmey Docklands Limited"
            assert provider.tram.operator.name == "Tram Operations Limited"
            captured = json.loads(body)
            for line, item in zip(provider.lines, captured, strict=True):
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.source_line_names == (item["name"],)
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
                for alert, status in zip(line.alerts, item["lineStatuses"]):
                    assert alert.description == status["reason"]
                    assert alert.affected_line_ids == (line.line_id,)
                    assert alert.language == "en"
                    assert alert.active_from is not None and alert.active_from.utcoffset() is not None
            assert not client.is_closed

    asyncio.run(scenario())


def test_real_later_capture_changes_lioness_to_suspended() -> None:
    first = (_FIXTURES / "tfl_live_20261104.json").read_bytes()
    later = (_FIXTURES / "tfl_live_20261104_130510.json").read_bytes()

    async def scenario() -> None:
        body = first
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body),
        )) as client:
            provider = TflProvider(client=client)
            await provider.refresh()
            previous = provider.lioness
            assert previous.status is LineStatus.PARTIAL_SUSPENSION
            body = later
            await provider.refresh()
            assert provider.lioness.status is LineStatus.SUSPENDED
            assert len(provider.lioness.alerts) == 1
            assert provider.lioness.alerts[0].effect is AlertEffect.NO_SERVICE
            assert provider.lioness.alerts[0].timing is AlertTiming.ACTIVE
            assert previous.status is LineStatus.PARTIAL_SUSPENSION and len(previous.alerts) == 2
            assert provider.central.source_status == "9: Minor Delays"

    asyncio.run(scenario())


def test_synthetic_reordered_lines_and_unknown_alongside_good_service() -> None:
    data = _synthetic()
    data[0]["lineStatuses"] = [_synthetic_status(), _synthetic_status(99, "New status")]
    data.reverse()
    parsed = _parse(_body(data), TflProvider().lines, _NOW)
    assert parsed[0].line_id == LineId("gb:london_underground:bakerloo")
    assert parsed[0].status is LineStatus.UNKNOWN
    assert parsed[0].alerts[0].effect is AlertEffect.UNKNOWN
    assert parsed[-1].line_id == LineId("gb:london_overground:windrush")
    assert parsed[-1].status is LineStatus.NORMAL


@pytest.mark.parametrize(("code", "label", "expected"), [
    (0, "Special Service", LineStatus.ALERT), (1, "Closed", LineStatus.SUSPENDED),
    (2, "Suspended", LineStatus.SUSPENDED), (3, "Part Suspended", LineStatus.PARTIAL_SUSPENSION),
    (4, "Planned Closure", LineStatus.ALERT), (5, "Part Closure", LineStatus.PARTIAL_SUSPENSION),
    (6, "Severe Delays", LineStatus.DELAYED), (7, "Reduced Service", LineStatus.PARTIAL_SUSPENSION),
    (8, "Bus Service", LineStatus.ALERT), (9, "Minor Delays", LineStatus.DELAYED),
    (10, "Good Service", LineStatus.NORMAL), (11, "Part Closed", LineStatus.PARTIAL_SUSPENSION),
    (12, "Exit Only", LineStatus.ALERT), (13, "No Step Free Access", LineStatus.ALERT),
    (14, "Change of frequency", LineStatus.ALERT), (15, "Diverted", LineStatus.ALERT),
    (16, "Not Running", LineStatus.SUSPENDED), (17, "Issues Reported", LineStatus.ALERT),
    (18, "No Issues", LineStatus.NORMAL), (19, "Information", LineStatus.ALERT),
    (20, "Service Closed", LineStatus.ALERT),
    (99, "New status", LineStatus.UNKNOWN), (10, "Suspended", LineStatus.UNKNOWN),
    (2, "Good Service", LineStatus.UNKNOWN), (10, "Good Service tomorrow", LineStatus.UNKNOWN),
])
def test_synthetic_dedicated_status_ignores_narrative(code: int, label: str, expected: LineStatus) -> None:
    data = _synthetic()
    data[0]["lineStatuses"] = [{**_synthetic_status(code, label),
        "reason": "SYNTHETIC: not suspended; yesterday's delays cleared; possible closure tomorrow."}]
    line = _parse(_body(data), TflProvider().lines, _NOW)[0]
    assert line.status is expected
    assert line.source_status == f"{code}: {label}"
    assert line.alerts[0].description.startswith("SYNTHETIC:")
    assert line.alerts[0].timing is AlertTiming.UNKNOWN
    assert line.alerts[0].active_from is line.alerts[0].active_until is None


def test_real_severity_metadata_supports_the_static_pairs_for_all_modes() -> None:
    from train_operation_info.providers.tfl.provider import _STATES

    data = json.loads((_FIXTURES / "tfl_severity_20261104.json").read_bytes())
    for mode in ("tube", "dlr", "overground", "elizabeth-line", "tram"):
        pairs = {(s["severityLevel"], s["description"]) for s in data if s["modeName"] == mode}
        assert set(_STATES) == pairs


def test_synthetic_disjoint_periods_are_separate_and_isnow_is_not_a_date_test() -> None:
    data = _synthetic()
    data[0]["lineStatuses"] = [{**_synthetic_status(3, "Part Suspended"), "validityPeriods": [
        {"fromDate": "2026-11-01T09:00:00Z", "toDate": "2026-11-01T10:00:00Z", "isNow": True},
        {"fromDate": "2026-11-04T09:00:00Z", "toDate": "2026-11-05T10:00:00Z", "isNow": False},
    ]}]
    line = _parse(_body(data), TflProvider().lines, _NOW)[0]
    assert line.status is LineStatus.PARTIAL_SUSPENSION
    assert len(line.alerts) == 2 and len({a.alert_id for a in line.alerts}) == 2
    assert line.alerts[0].timing is AlertTiming.ACTIVE
    assert line.alerts[1].timing is AlertTiming.UNKNOWN
    assert line.alerts[0].active_until is not None and line.alerts[1].active_from is not None
    assert line.alerts[0].active_until < line.alerts[1].active_from


@pytest.mark.parametrize("damage", [
    "empty", "missing", "duplicate", "unknown_line", "mode", "missing_status", "empty_status",
    "string_severity", "bool_severity", "missing_label", "empty_label", "foreign_status",
    "missing_periods", "naive_time", "reversed_period", "string_isnow", "invalid_json",
])
def test_synthetic_damage_preserves_previous_snapshot(damage: str) -> None:
    data = _synthetic()
    status = _synthetic_status(2, "Suspended")
    if damage == "empty":
        data = []
    elif damage == "missing":
        data.pop()
    elif damage == "duplicate":
        data.append(data[0])
    elif damage == "unknown_line":
        data[0]["id"] = "new-line"
    elif damage == "mode":
        data[0]["modeName"] = "bus"
    elif damage == "missing_status":
        del data[0]["lineStatuses"]
    elif damage == "empty_status":
        data[0]["lineStatuses"] = []
    else:
        if damage == "string_severity":
            status["statusSeverity"] = "2"
        elif damage == "bool_severity":
            status["statusSeverity"] = True
        elif damage == "missing_label":
            del status["statusSeverityDescription"]
        elif damage == "empty_label":
            status["statusSeverityDescription"] = ""
        elif damage == "foreign_status":
            status["lineId"] = "district"
        elif damage == "missing_periods":
            del status["validityPeriods"]
        else:
            period: dict[str, object] = {
                "fromDate": "2026-11-04T01:00:00Z", "toDate": "2026-11-04T02:00:00Z", "isNow": True,
            }
            if damage == "naive_time":
                period["fromDate"] = "2026-11-04T01:00:00"
            elif damage == "reversed_period":
                period["toDate"] = "2026-11-03T01:00:00Z"
            elif damage == "string_isnow":
                period["isNow"] = "true"
            status["validityPeriods"] = [period]
        data[0]["lineStatuses"] = [status]
    broken_body = b"not JSON" if damage == "invalid_json" else _body(data)

    async def scenario() -> None:
        broken = False
        healthy = _synthetic()
        healthy[0]["lineStatuses"] = [_synthetic_status(2, "Suspended")]
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=broken_body if broken else _body(healthy)),
        )) as client:
            provider = TflProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous and provider.bakerloo.status is LineStatus.SUSPENDED

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "transport"])
def test_synthetic_failure_and_recovery_clear_old_alerts(failure: str) -> None:
    async def scenario() -> None:
        phase = 0

        def handler(request: httpx.Request) -> httpx.Response:
            if phase == 1:
                if failure == "transport":
                    raise httpx.ConnectError("synthetic offline", request=request)
                return httpx.Response(429)
            data = _synthetic()
            if phase == 0:
                data[0]["lineStatuses"] = [_synthetic_status(2, "Suspended")]
            return httpx.Response(200, content=_body(data))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TflProvider(client=client)
            await provider.refresh()
            old = provider.bakerloo
            phase = 1
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.bakerloo is old
            phase = 2
            await provider.refresh()
            assert provider.bakerloo.status is LineStatus.NORMAL and not provider.alerts
            assert old.status is LineStatus.SUSPENDED and old.alerts

    asyncio.run(scenario())


def test_tracker_override_selection_and_independent_failure() -> None:
    async def scenario() -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return (httpx.Response(200, content=_body(_synthetic())) if str(request.url) == _URL
                    else httpx.Response(503))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tfl = TflProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(tfl,))
            await disabled.refresh()
            assert not requested
            tracker = Tracker(enabled_providers=("tfl", "osaka_metro"), client=client, overrides=(tfl,))
            with pytest.raises(RefreshError) as exc:
                await tracker.refresh()
            assert set(exc.value.errors) == {"osaka_metro"}
            assert tracker.tfl is tfl and tracker.tfl.bakerloo.status is LineStatus.NORMAL
            assert tracker.tfl.bakerloo.line_id == LineId("gb:london_underground:bakerloo")

    asyncio.run(scenario())
