"""Real JR Central delay/normal captures; altered states/failures are synthetic."""

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertTiming, LineId, LineStatus, UsagePermission
from train_operation_info.providers.jrcentral import JrCentralProvider

_FIXTURES = Path(__file__).parent / "fixtures"


def _original() -> dict[str, object]:
    # Strict parsing is tested inside the provider; this annotation is test input.
    result: dict[str, object] = json.loads((_FIXTURES / "jrcentral_operation.json").read_bytes())
    return result


def _response(request: httpx.Request, payload: bytes) -> httpx.Response:
    if request.url.path.endswith("hp_service_jotai_kanri.json"):
        return httpx.Response(200, content=(_FIXTURES / "jrcentral_service.json").read_bytes())
    assert request.url.path == "/zairaisen/data/trainInfo/json/unkou.json"
    return httpx.Response(200, content=payload)


@pytest.mark.parametrize("fixture", [
    "jrcentral_operation.json", "jrcentral_history_60741.json",
    "jrcentral_history_60740.json", "jrcentral_history_60739.json",
])
def test_real_delays_and_shared_identity(fixture: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, (_FIXTURES / fixture).read_bytes()),
        )) as client:
            tracker = Tracker(enabled_providers=("jrcentral",), client=client)
            yahoo_before = tracker.yahoo.lines
            await tracker.refresh()
            provider = tracker.jrcentral
            assert len(provider.lines) == 13
            assert provider.tokaido_atami_toyohashi.status is LineStatus.DELAYED
            assert provider.tokaido_atami_toyohashi.line_id == LineId("jp:jr_central:line_6fc336cf9ff1")
            assert provider.tokaido_atami_toyohashi.alerts
            assert "富士" in provider.tokaido_atami_toyohashi.alerts[0].description
            assert provider.chuo.line_id != LineId("jp:jr_central:line_5f4d2a9ef7e9")
            assert provider.chuo.name == "中央本線[名古屋～塩尻]"
            assert provider.chuo.source_line_names == ("中央線",)
            assert all(line.updated_at is None for line in provider.lines)
            assert all(line.fetched_at is not None and line.fetched_at.utcoffset() is not None for line in provider.lines)
            assert all(alert.timing is AlertTiming.UNKNOWN for alert in provider.alerts)
            other = tracker.yahoo.get_line(provider.tokaido_atami_toyohashi.line_id)
            assert other is not None and other is not provider.tokaido_atami_toyohashi
            assert other.operator is provider.tokaido_atami_toyohashi.operator
            assert tracker.yahoo.lines is yahoo_before
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED

    asyncio.run(scenario())


@pytest.mark.parametrize(("code", "state"), [
    ("0001", LineStatus.SUSPENDED), ("0002", LineStatus.SUSPENDED),
    ("0003", LineStatus.SUSPENDED), ("0004", LineStatus.SUSPENDED),
    ("0005", LineStatus.ALERT), ("0006", LineStatus.DELAYED),
    ("0007", LineStatus.ALERT), ("0009", LineStatus.NORMAL),
    ("future-code", LineStatus.UNKNOWN),
])
def test_synthetic_codes_use_official_detail_mapping_without_reading_prose(code: str, state: LineStatus) -> None:
    payload = (_FIXTURES / "jrcentral_operation.json").read_text(encoding="utf-8-sig")
    payload = payload.replace('"status_id":"0006"', f'"status_id":"{code}"')

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, payload.encode()),
        )) as client:
            provider = JrCentralProvider(client=client)
            await provider.refresh()
            line = provider.tokaido_atami_toyohashi
            assert line.status is state
            assert "遅れが発生" in line.alerts[0].description
            assert line.alerts[0].timing is AlertTiming.UNKNOWN
            assert line.alerts[0].affected_line_ids == (line.line_id,)

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["missing", "type", "null_incident", "unknown_route", "unpaired", "duplicate", "missing_ja", "normal_conflict", "maintenance", "http"])
def test_synthetic_failure_preserves_entire_snapshot(kind: str) -> None:
    payload = (_FIXTURES / "jrcentral_operation.json").read_text(encoding="utf-8-sig")
    changed = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not changed:
            return _response(request, payload.encode())
        if request.url.path.endswith("hp_service_jotai_kanri.json"):
            return httpx.Response(200, json={"serviceJotai": "1" if kind == "maintenance" else "0"})
        data = _original()
        if kind == "missing":
            del data["events"]
        elif kind == "type":
            data["events"] = "not a list"
        elif kind == "unpaired":
            data["message_info"] = []
        elif kind == "null_incident":
            data["events"] = None
            data["message_info"] = None
        elif kind == "normal_conflict":
            data["check"] = "0"
        elif kind == "http":
            return httpx.Response(503)
        elif kind == "duplicate":
            events = data["events"]
            assert isinstance(events, list)
            data["events"] = events + deepcopy(events)
        else:
            altered = payload.replace("東海道線(熱海～豊橋)", "未登録線") if kind == "unknown_route" else payload.replace('"lang":"ja"', '"lang":"xx"')
            return httpx.Response(200, content=altered.encode())
        return httpx.Response(200, json=data)

    async def scenario() -> None:
        nonlocal changed
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrCentralProvider(client=client)
            await provider.refresh()
            before = provider.lines
            changed = True
            with pytest.raises(FetchError if kind == "http" else ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_real_normal_clears_alerts_and_injected_provider_stays_disabled() -> None:
    recovery = False
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        payload = ((_FIXTURES / "jrcentral_normal.json").read_bytes() if recovery else
                   (_FIXTURES / "jrcentral_operation.json").read_bytes())
        return _response(request, payload)

    async def scenario() -> None:
        nonlocal recovery
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrCentralProvider(client=client)
            tracker = Tracker(enabled_providers=(), overrides=(provider,))
            assert tracker.jrcentral is provider
            await tracker.refresh()
            assert calls == []
            assert any(p.provider_id == "jrcentral" for p in Tracker().providers)
            await provider.refresh()
            assert provider.alerts
            recovery = True
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert provider.alerts == () and provider.delay_lines == ()

    asyncio.run(scenario())


def test_saved_evidence_hashes() -> None:
    manifest = json.loads((_FIXTURES / "jrcentral_manifest.json").read_text(encoding="utf-8"))
    for record in manifest:
        assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record["fixture_sha256"]
        assert record["original_sha256"] == record["fixture_sha256"]


@pytest.mark.parametrize("panel", ["その他・ホームライナーなど", "しなの"])
def test_synthetic_excluded_blank_content_does_not_block_covered_delays(panel: str) -> None:
    # Synthetic reproduction of empty content in known, excluded panels.
    route = "東海道線(豊橋～米原)"
    payload = {
        "check": "1",
        "events": [
            {"no": "1", "imp_line": [{"lang": "ja", "name": route}],
             "status_id": "0006", "status": [{"lang": "ja", "name": "遅れ／運休あり"}]},
            {"no": "2", "imp_line": [{"lang": "ja", "name": panel}],
             "status_id": "unused", "status": [{"lang": "ja", "name": ""}]},
        ],
        "message_info": [
            {"trainline": [{"lang": "ja", "name": route}],
             "delivery_msg": [{"lang": "ja", "message": "合成：対象路線の案内"}]},
            {"trainline": [{"lang": "ja", "name": panel}],
             "delivery_msg": [{"lang": "ja", "message": ""}]},
            {"trainline": [{"lang": "ja", "name": panel}],
             "delivery_msg": [{"lang": "ja", "message": ""}]},
        ],
    }

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=(
                {"serviceJotai": "0"} if request.url.path.endswith("hp_service_jotai_kanri.json") else payload
            )),
        )) as client:
            provider = JrCentralProvider(client=client)
            await provider.refresh()
            line = provider.tokaido_toyohashi_maibara
            assert line.status is LineStatus.DELAYED
            assert line.alerts[0].description == "合成：対象路線の案内"
            assert len(provider.alerts) == 1
            assert len(provider.lines) == 13
            assert len(provider.delay_lines) == 1
            assert len([line for line in provider.lines if line.status is LineStatus.NORMAL]) == 12

    asyncio.run(scenario())


@pytest.mark.parametrize("route, message, error", [
    ("東海道線(豊橋～米原)", "", "Japanese message"),
    ("合成：未知の路線", "", "Unregistered JR Central route"),
])
def test_synthetic_blank_message_is_not_ignored_for_covered_or_unknown_routes(
    route: str, message: str, error: str,
) -> None:
    async def scenario() -> None:
        data: dict[str, object] = {"check": "0", "events": None, "message_info": None}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=(
                {"serviceJotai": "0"} if request.url.path.endswith("hp_service_jotai_kanri.json") else data
            )),
        )) as client:
            provider = JrCentralProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            data.update(check="1", events=[], message_info=[{
                "trainline": [{"lang": "ja", "name": route}],
                "delivery_msg": [{"lang": "ja", "message": message}],
            }])
            with pytest.raises(ParseError, match=error):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_live_capture_with_empty_excluded_liner_messages() -> None:
    payload = (_FIXTURES / "jrcentral_operation_20261107T150825Z.json").read_bytes()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, payload),
        )) as client:
            provider = JrCentralProvider(client=client)
            await provider.refresh()
            assert len(provider.lines) == 13
            line = provider.tokaido_toyohashi_maibara
            assert line.status is LineStatus.DELAYED
            assert len(line.alerts) == 2
            assert all(alert.description for alert in line.alerts)
            assert all(alert.affected_line_ids == (line.line_id,) for alert in provider.alerts)

    asyncio.run(scenario())
