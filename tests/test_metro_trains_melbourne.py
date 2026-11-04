"""Live normal/works capture and explicitly synthetic source-based scenarios."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import JsonValue

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, LineId, LineStatus, UsagePermission,
)
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.metro_trains_melbourne import MetroTrainsMelbourneProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_ROUTES = (
    ("82", "Alamein"), ("84", "Belgrave"), ("85", "Craigieburn"),
    ("86", "Cranbourne"), ("87", "Mernda"), ("88", "Frankston"),
    ("89", "Glen Waverley"), ("90", "Hurstbridge"), ("91", "Lilydale"),
    ("92", "Pakenham"), ("93", "Sandringham"), ("94", "Stony Point"),
    ("95", "Sunbury"), ("96", "Upfield"), ("97", "Werribee"),
    ("98", "Williamstown"), ("168307", "Racecourse"),
)
_NORMAL = "Good service - trains are running on time"


def _synthetic() -> dict[str, JsonValue]:
    return {code: {"line_name": name, "alerts": _NORMAL} for code, name in _ROUTES}


def _network() -> dict[str, JsonValue]:
    return {"network": [{"lines": [
        {"id": code, "name": name, "active": code != "168307"} for code, name in _ROUTES
    ]}]}


def _line(data: dict[str, JsonValue], code: str = "82") -> dict[str, JsonValue]:
    value = data[code]
    assert isinstance(value, dict)
    return value


def _alert(code: str) -> dict[str, JsonValue]:
    return {
        "alert_type": code, "alert_text": "<p>Synthetic notice.</p>",
        "from_date": "1793789400", "to_date": "1793804400",
    }


def _response(request: httpx.Request, data: dict[str, JsonValue]) -> httpx.Response:
    assert request.url.host == "www.metrotrains.com.au"
    assert request.url.path == "/api" and request.method == "GET"
    assert request.headers["User-Agent"] == USER_AGENT
    if request.url.params["op"] == "get_network":
        assert request.url.params["config"] == "Aug26"
        return httpx.Response(200, json=_network())
    assert request.url.params["op"] == "get_healthboard_alerts"
    return httpx.Response(200, json=data)


def test_official_capture_and_tracker_integration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        part = "network" if request.url.params["op"] == "get_network" else "healthboard"
        return httpx.Response(200, content=(
            _FIXTURES / f"metro_trains_melbourne_{part}.json"
        ).read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("metro_trains_melbourne",), client=client)
            provider = tracker.metro_trains_melbourne
            assert len(tracker.unknown_lines) == 17
            await tracker.refresh()
            assert len(provider.lines) == 17 and not tracker.unknown_lines
            assert provider.werribee.status is LineStatus.ALERT
            assert sum(line.status is LineStatus.NORMAL for line in provider.lines) == 16
            assert provider.racecourse.source_status == "no-services"
            for line, (_, name) in zip(provider.lines, _ROUTES, strict=True):
                key = name.lower().replace(" ", "_")
                assert line is getattr(provider, key)
                assert line.line_id == LineId(f"au:metro_trains_melbourne:{key}")
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.name == f"{name} Line"
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
                assert line.updated_at is None
            assert provider.werribee.alerts[0].effect is AlertEffect.OTHER
            assert provider.werribee.alerts[0].active_from == datetime.fromtimestamp(1793789400, timezone.utc)
            assert not provider.active_alerts
            assert provider.metadata.usage_permission is UsagePermission.UNSPECIFIED
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("code", "expected", "effect"), [
    ("minor", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("major", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("suspended", LineStatus.PARTIAL_SUSPENSION, AlertEffect.REDUCED_SERVICE),
    ("works", LineStatus.ALERT, AlertEffect.OTHER),
    ("travel", LineStatus.ALERT, AlertEffect.OTHER),
    ("service", LineStatus.ALERT, AlertEffect.OTHER),
    ("cancellation", LineStatus.ALERT, AlertEffect.OTHER),
    ("trip", LineStatus.ALERT, AlertEffect.OTHER),
    ("good-service", LineStatus.NORMAL, AlertEffect.OTHER),
    ("good", LineStatus.NORMAL, AlertEffect.OTHER),
    ("no-services", LineStatus.NORMAL, AlertEffect.OTHER),
    ("new-category", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
])
def test_synthetic_categories_and_recovery(
    code: str, expected: LineStatus, effect: AlertEffect,
) -> None:
    data = _synthetic()
    item = _alert(code)
    item["alert_text"] = "<p>Synthetic: Belgrave suspended tomorrow; service resumed.</p>"
    item["altered_services_text"] = "<p>Synthetic additional details.</p>"
    _line(data)["alerts"] = [item]

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, data),
        )) as client:
            provider = MetroTrainsMelbourneProvider(client=client)
            await provider.refresh()
            previous = provider.alamein
            assert previous.status is expected and previous.source_status == code
            assert provider.belgrave.status is LineStatus.NORMAL
            alert, = previous.alerts
            assert alert.effect is effect and alert.language == "en"
            assert alert.affected_line_ids == (previous.line_id,)
            assert alert.timing is AlertTiming.UNKNOWN
            assert alert.active_from == datetime.fromtimestamp(1793789400, timezone.utc)
            assert alert.active_until == datetime.fromtimestamp(1793804400, timezone.utc)
            assert "additional details" in alert.description and "<p>" not in alert.description
            _line(data)["alerts"] = _NORMAL
            await provider.refresh()
            assert provider.alamein.status is LineStatus.NORMAL and not provider.alerts
            assert provider.alamein is not previous and previous.status is expected

    asyncio.run(scenario())


def test_synthetic_multiple_notices_and_structured_disruption() -> None:
    data = _synthetic()
    _line(data)["alerts"] = [_alert("minor"), _alert("good-service"), _alert("works")]
    disruption: dict[str, JsonValue] = {
        "lines": ["82", "84"], "alert_type": "suspended", "notice": "Synthetic shared notice.",
        "from_date": None, "to_date": "0",
    }
    data["disruptions"] = {"synthetic": disruption}

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, data),
        )) as client:
            provider = MetroTrainsMelbourneProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.PARTIAL_SUSPENSION for line in (provider.alamein, provider.belgrave))
            assert len(provider.alamein.alerts) == 4 and len(provider.alerts) == 4
            alert = provider.belgrave.alerts[0]
            assert alert.affected_line_ids == (provider.alamein.line_id, provider.belgrave.line_id)
            assert alert.active_from is alert.active_until is None
            data["disruptions"] = []
            await provider.refresh()
            assert provider.alamein.status is LineStatus.DELAYED
            assert provider.belgrave.status is LineStatus.NORMAL and not provider.belgrave.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("raw_status", ["Synthetic unfamiliar status", "minor", "good"])
def test_synthetic_separate_collections_and_unknown_normal_string(raw_status: str) -> None:
    data = _synthetic()
    _line(data)["planned_works_list"] = [{"title": "Synthetic suspended forever"}]
    data["general"] = {"title": "Synthetic network announcement"}
    data["lift_escalator_outages"] = [{"station": "Synthetic"}]
    _line(data, "84")["alerts"] = raw_status
    _line(data, "168307")["no_services"] = "Synthetic special-event services only."

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, data),
        )) as client:
            provider = MetroTrainsMelbourneProvider(client=client)
            await provider.refresh()
            assert provider.alamein.status is LineStatus.NORMAL and not provider.alamein.alerts
            assert provider.belgrave.status is LineStatus.UNKNOWN
            assert provider.belgrave.alerts[0].description == raw_status
            assert provider.belgrave.alerts[0].effect is AlertEffect.UNKNOWN
            assert provider.racecourse.status is LineStatus.NORMAL
            assert provider.racecourse.source_status == "no-services"

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [
    "missing_route", "unknown_route", "wrong_name", "missing_alerts", "null_alerts",
    "wrong_type", "missing_text", "empty_text", "missing_code", "conflicting_route",
    "missing_date", "bad_date", "huge_date", "reversed_period", "unknown_disruption_route",
    "empty_disruption_routes", "bad_disruptions", "network_roster", "duplicate_network_route",
    "network_name", "network_active", "maintenance", "http", "connection",
])
def test_synthetic_failures_keep_previous_snapshot(failure: str) -> None:
    data = _synthetic()
    network = _network()
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken and failure == "connection":
            raise httpx.ConnectError("Synthetic failure", request=request)
        if broken and failure == "http":
            return httpx.Response(503)
        if broken and failure == "maintenance":
            return httpx.Response(200, text="<html>Synthetic maintenance</html>")
        return httpx.Response(200, json=network) if request.url.params["op"] == "get_network" else _response(request, data)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = MetroTrainsMelbourneProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            item = _alert("minor")
            _line(data)["alerts"] = [item]
            if failure == "missing_route":
                del data["84"]
            elif failure == "unknown_route":
                data["999"] = {"alerts": _NORMAL}
            elif failure == "wrong_name":
                _line(data)["line_name"] = "Synthetic wrong route"
            elif failure == "missing_alerts":
                del _line(data)["alerts"]
            elif failure == "null_alerts":
                _line(data)["alerts"] = None
            elif failure == "wrong_type":
                item["alert_type"] = 1
            elif failure == "missing_text":
                del item["alert_text"]
            elif failure == "empty_text":
                item["alert_text"] = "<p> </p>"
            elif failure == "missing_code":
                del item["alert_type"]
            elif failure == "conflicting_route":
                item["line_id"] = "84"
            elif failure == "missing_date":
                del item["from_date"]
            elif failure == "bad_date":
                item["from_date"] = "tomorrow"
            elif failure == "huge_date":
                item["from_date"] = "9" * 100
            elif failure == "reversed_period":
                item["to_date"] = "1"
            elif failure in ("unknown_disruption_route", "empty_disruption_routes"):
                data["disruptions"] = [{
                    "lines": ["999"] if failure == "unknown_disruption_route" else [],
                    "alert_type": "suspended", "notice": "Synthetic", "from_date": "", "to_date": "",
                }]
            elif failure == "bad_disruptions":
                data["disruptions"] = None
            elif failure.startswith("network_") or failure == "duplicate_network_route":
                groups = network["network"]
                assert isinstance(groups, list)
                group = groups[0]
                assert isinstance(group, dict)
                routes = group["lines"]
                assert isinstance(routes, list)
                route = routes[0]
                assert isinstance(route, dict)
                if failure == "network_roster":
                    routes.pop()
                elif failure == "duplicate_network_route":
                    routes[-1] = route
                elif failure == "network_name":
                    route["name"] = "Synthetic renamed route"
                else:
                    route["active"] = "true"
            broken = True
            with pytest.raises(FetchError if failure in ("http", "connection") else ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())
