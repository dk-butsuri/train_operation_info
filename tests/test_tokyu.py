"""Live official normal JSON; all abnormal mutations below are synthetic."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, AlertEffect, LineStatus, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.tokyu import TokyuProvider
from train_operation_info.providers.yahoo import YahooProvider, YahooRouteId

_FIXTURES = Path(__file__).parent / "fixtures"
_BASE = "https://www.tokyu.co.jp/unten/"


def _payload() -> dict[str, object]:
    # Test fixture data is deliberately untyped until validated by the provider.
    data: dict[str, object] = json.loads((_FIXTURES / "tokyu_normal.json").read_text("utf-8-sig"))
    return data


def _response(request: httpx.Request, payload: dict[str, object] | None = None) -> httpx.Response:
    assert request.method == "GET"
    assert request.headers["User-Agent"] == USER_AGENT
    fixtures = {
        _BASE + "unten2.json": "tokyu_normal.json",
        _BASE + "unten_additional.json": "tokyu_additional_normal.json",
        _BASE + "information.json": "tokyu_information_normal.json",
    }
    fixture = fixtures[str(request.url)]
    if payload is not None and fixture == "tokyu_normal.json":
        return httpx.Response(200, json=payload)
    return httpx.Response(200, content=(_FIXTURES / fixture).read_bytes())


def test_official_normal_and_canonical_ids() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_response)) as client:
            provider = TokyuProvider(client=client)
            tracker = Tracker(enabled_providers=("tokyu",), overrides=(provider,))
            assert tracker.providers == (provider,)
            assert len(tracker.unknown_lines) == 9
            await tracker.refresh()
            assert len(tracker.lines) == 9
            assert len({line.line_id for line in provider.lines}) == 9
            assert all(line.status is LineStatus.NORMAL for line in tracker.lines)
            assert not tracker.alerts and not tracker.affected_lines
            assert provider.lines == (
                provider.toyoko, provider.meguro, provider.shin_yokohama,
                provider.den_en_toshi, provider.oimachi, provider.ikegami,
                provider.tamagawa, provider.setagaya, provider.kodomonokuni,
            )
            for line in provider.lines:
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.operator.name == "東急電鉄"
                assert line.updated_at is None
                assert line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                assert line.source_line_names
            other = YahooProvider().get_source_line(YahooRouteId("112/0"))
            assert other is not None
            assert other.line_id == provider.toyoko.line_id
            assert other.operator is provider.toyoko.operator
            assert other.status is LineStatus.UNKNOWN
            assert other is not provider.toyoko
            assert provider.metadata.usage_permission is UsagePermission.PRIVATE_USE_ONLY
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("code", "status", "effect"), [
    ("1,1", LineStatus.ALERT, AlertEffect.OTHER),
    ("2,2", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
    ("1,3", LineStatus.ALERT, AlertEffect.OTHER),
    ("1,9", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
    ("9,0", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
])
def test_synthetic_incident_codes_and_recovery(code: str, status: LineStatus, effect: AlertEffect) -> None:
    payload = _payload()
    payload.update(check="1", check_ty=code, unten_ty="試験の運行案内。<br>運転を再開しました。")
    payload["kousin_jikoku"] = "synthetic unverified timestamp"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: _response(request, payload))) as client:
            tracker = Tracker(enabled_providers=("tokyu",), client=client)
            await tracker.refresh()
            line = tracker.tokyu.toyoko
            assert line.status is status
            assert line.alerts[0].effect is effect
            assert line.alerts[0].affected_line_ids == (line.line_id,)
            assert "試験の運行案内。\n運転を再開しました。" in line.alerts[0].description
            assert "synthetic unverified timestamp" in line.alerts[0].description
            assert code in (line.source_status or "")
            assert line.updated_at is None
            assert all(other.status is LineStatus.NORMAL for other in tracker.lines[1:])
            payload.clear()
            payload.update(_payload())
            await tracker.refresh()
            assert not tracker.alerts and not tracker.affected_lines
            assert all(other.status is LineStatus.NORMAL for other in tracker.lines)
            assert line.status is status  # previous snapshots remain immutable

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "missing_route", "missing_message", "empty_message", "wrong_type",
    "bad_code", "missing_check", "missing_time", "conflicting_normal",
    "invalid_json", "http_error", "transport_error", "broken_additional",
    "broken_information",
])
def test_synthetic_failures_preserve_previous_snapshot(fault: str) -> None:
    broken = False
    payload = _payload()
    if fault == "missing_route":
        del payload["check_kd"]
    elif fault == "missing_message":
        del payload["unten_ty"]
    elif fault == "empty_message":
        payload["unten_ty"] = " "
    elif fault == "wrong_type":
        payload["check_ty"] = 0
    elif fault == "bad_code":
        payload["check_ty"] = "2"
    elif fault == "missing_check":
        del payload["check"]
    elif fault == "missing_time":
        del payload["kousin_jikoku"]
    elif fault == "conflicting_normal":
        payload["check_ty"] = "2,2"

    def handler(request: httpx.Request) -> httpx.Response:
        if not broken:
            return _response(request)
        if fault == "http_error":
            return httpx.Response(503)
        if fault == "transport_error":
            raise httpx.ConnectError("synthetic", request=request)
        if fault == "invalid_json":
            return httpx.Response(200, text="<html>maintenance</html>")
        if fault == "broken_additional" and request.url.path.endswith("unten_additional.json"):
            return httpx.Response(200, json={})
        if fault == "broken_information" and request.url.path.endswith("information.json"):
            return httpx.Response(200, json={"check": "1", "message": ""})
        return _response(request, payload)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TokyuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            expected = FetchError if fault in ("http_error", "transport_error") else ParseError
            with pytest.raises(expected):
                await provider.refresh()
            assert provider.lines is previous
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["additional", "information", "unknown_global", "unscoped", "contradictory_message"])
def test_synthetic_unidentified_notices_and_unknown_states(kind: str) -> None:
    payload = _payload()
    if kind == "unknown_global":
        payload["check"] = "9"
    elif kind == "unscoped":
        payload.update(check="1", unten="対象路線未特定の運行情報")
    elif kind == "contradictory_message":
        payload["unten_ty"] = "平常表示と異なる未確認の案内"

    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "additional" and request.url.path.endswith("unten_additional.json"):
            return httpx.Response(200, json={"message": "対象路線未特定のお知らせ"})
        if kind == "information" and request.url.path.endswith("information.json"):
            return httpx.Response(200, json={"check": "1", "message": "対象路線未特定のお知らせ"})
        return _response(request, payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TokyuProvider(client=client)
            await provider.refresh()
            assert provider.toyoko.status is LineStatus.UNKNOWN
            assert provider.alerts
            if kind in ("additional", "information", "unscoped"):
                assert len(provider.alerts) == 1
                assert provider.alerts[0].affected_line_ids == ()
            if kind == "contradictory_message":
                assert provider.meguro.status is LineStatus.NORMAL

    asyncio.run(scenario())


def test_tracker_selection_default_and_failure_isolation() -> None:
    requests: list[str] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(503) if fail else _response(request)

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TokyuProvider(client=client)
            assert "tokyu" in {p.provider_id for p in Tracker().providers}
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert requests == []
            tracker = Tracker(enabled_providers=("tokyu",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {provider.provider_id}
            assert provider.lines is previous
            assert len(requests) == 4

    asyncio.run(scenario())
