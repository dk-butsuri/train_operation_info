"""Official archived responses; mutations below are explicitly synthetic."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertTiming, LineStatus, ProviderId
from train_operation_info.providers.odakyu import OdakyuProvider

_FIXTURES = Path(__file__).parent / "fixtures"


def _response(request: httpx.Request, payload: bytes) -> httpx.Response:
    if request.url.path == "/train_status":
        filename = "odakyu_page.html"
    elif request.url.path == "/assets/index-yuMM9dEt.js":
        filename = "odakyu_app_excerpt.js"
    else:
        assert str(request.url) == "https://d6oynijiy33tb.cloudfront.net/service/status_detail"
        assert request.headers["x-api-key"]
        return httpx.Response(200, content=payload)
    return httpx.Response(200, content=(_FIXTURES / filename).read_bytes())


@pytest.mark.parametrize(("filename", "states"), [
    ("odakyu_normal.json", (LineStatus.NORMAL,) * 3),
    ("odakyu_20250710071411.json", (LineStatus.NORMAL,) * 3),
    ("odakyu_20250730090750.json", (LineStatus.UNKNOWN, LineStatus.PARTIAL_SUSPENSION, LineStatus.UNKNOWN)),
    ("odakyu_20251124012021.json", (LineStatus.PARTIAL_SUSPENSION, LineStatus.DELAYED, LineStatus.DELAYED)),
    ("odakyu_20251126033118.json", (LineStatus.NORMAL, LineStatus.PARTIAL_SUSPENSION, LineStatus.NORMAL)),
    ("odakyu_20260128234609.json", (LineStatus.DELAYED, LineStatus.UNKNOWN, LineStatus.UNKNOWN)),
    ("odakyu_20260728134022.json", (LineStatus.DELAYED, LineStatus.DELAYED, LineStatus.NORMAL)),
    ("odakyu_20261014200025.json", (LineStatus.NORMAL,) * 3),
])
def test_official_archives_and_canonical_identity(filename: str, states: tuple[LineStatus, ...]) -> None:
    payload = (_FIXTURES / filename).read_bytes()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _response(r, payload))) as client:
            tracker = Tracker(enabled_providers=("odakyu",), client=client)
            before = tracker.yahoo.lines
            await tracker.refresh()
            provider = tracker.odakyu
            assert tuple(line.status for line in provider.lines) == states
            assert (provider.odawara, provider.enoshima, provider.tama) == provider.lines
            for line in provider.lines:
                other = next(v for v in before if v.line_id == line.line_id)
                assert other is not line
                assert other.operator is line.operator
                assert other.status is LineStatus.UNKNOWN
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
            if "train_service_status_detail" in json.loads(payload):
                assert provider.odawara.updated_at is not None
                assert provider.odawara.updated_at.isoformat() == json.loads(payload)["train_service_status_detail"]["update_time"].replace(".000Z", "+00:00")
            else:
                assert provider.odawara.updated_at is None
            assert all(alert.timing is AlertTiming.UNKNOWN for alert in provider.alerts)

    asyncio.run(scenario())


def test_archived_disruption_is_cleared_by_archived_normal_state() -> None:
    payload = (_FIXTURES / "odakyu_20250730090750.json").read_bytes()

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _response(r, payload))) as client:
            provider = OdakyuProvider(client=client)
            await provider.refresh()
            assert provider.enoshima.status is LineStatus.PARTIAL_SUSPENSION
            assert any(not alert.affected_line_ids for alert in provider.alerts)
            payload = (_FIXTURES / "odakyu_20261014200025.json").read_bytes()
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert provider.alerts == ()

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "type", "date", "no_blocks", "no_detail"])
def test_synthetic_malformed_data_preserves_previous_snapshot(mutation: str) -> None:
    payload = (_FIXTURES / "odakyu_20260728134022.json").read_bytes()

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _response(r, payload))) as client:
            provider = OdakyuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            data = json.loads(payload)
            if mutation == "missing":
                data["influence_block_state"].pop(0)
            elif mutation == "duplicate":
                data["influence_block_state"].append(data["influence_block_state"][0])
            elif mutation == "type":
                data["influence_block_state"][0]["up_state"] = "1"
            elif mutation == "date":
                data["train_service_status_detail"]["update_time"] = "2026-07-28T13:36:40"
            elif mutation == "no_blocks":
                data["influence_block_state"] = []
            else:
                del data["train_service_status_detail"]
            payload = json.dumps(data).encode()
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["suspension", "unknown", "unknown_scope", "maintenance", "future_text", "notice"])
def test_synthetic_states_do_not_infer_from_prose(case: str) -> None:
    data = json.loads((_FIXTURES / "odakyu_20260728134022.json").read_bytes())
    for block in data["influence_block_state"]:
        block["up_state"] = block["down_state"] = 0
    detail = data["train_service_status_detail"]
    detail["hp_influence_status_odawara"] = ""
    detail["hp_influence_status_enoshima"] = ""
    if case == "suspension":
        for block in data["influence_block_state"][:17]:
            block["up_state"] = 2
    elif case == "unknown":
        data["influence_block_state"][0]["up_state"] = 99
    elif case == "unknown_scope":
        data["influence_block_state"][-1]["block_state"] = 99
    elif case == "maintenance":
        data["status"][0]["status"] = 21
    elif case == "future_text":
        detail["hp_status"] = "明日は運転を見合わせます。運休との案内は取り消しました。"
    else:
        detail["hp_influence_status_tama"] = "運行情報をご確認ください。"
    payload = json.dumps(data).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _response(r, payload))) as client:
            provider = OdakyuProvider(client=client)
            await provider.refresh()
            expected = LineStatus.SUSPENDED if case == "suspension" else LineStatus.UNKNOWN
            assert provider.odawara.status is expected
            if case == "notice":
                assert provider.tama.status is LineStatus.ALERT
            if case == "future_text":
                assert any("明日は" in alert.description and not alert.affected_line_ids for alert in provider.alerts)
            if case == "unknown":
                assert "99" in (provider.odawara.source_status or "")
            if case == "unknown_scope":
                assert provider.alerts
                assert all(not alert.affected_line_ids for alert in provider.alerts)

    asyncio.run(scenario())


def test_selection_injection_and_fetch_failure() -> None:
    requests: list[str] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(503) if fail else _response(request, (_FIXTURES / "odakyu_normal.json").read_bytes())

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OdakyuProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not requests
            tracker = Tracker(enabled_providers=("odakyu",), overrides=(provider,))
            assert tracker.providers == (provider,)
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.provider_id == ProviderId("odakyu")

    asyncio.run(scenario())
