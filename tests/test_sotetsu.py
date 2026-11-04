"""Archived/live evidence and explicitly synthetic protocol/error cases."""

import asyncio
from datetime import timedelta
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertTiming, LineId, LineStatus, ProviderId
from train_operation_info.providers.sotetsu import SotetsuProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_FEED = "https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json"


@pytest.mark.parametrize(("name", "status"), [
    ("normal", LineStatus.NORMAL),
    ("20230717075741", LineStatus.ALERT),
    ("20230729083512", LineStatus.NORMAL),
    ("20260519070818", LineStatus.NORMAL),
])
def test_official_captures_and_later_normal(name: str, status: LineStatus) -> None:
    payload = (_FIXTURES / f"sotetsu_{name}.json").read_bytes()
    normal = (_FIXTURES / "sotetsu_normal.json").read_bytes()

    async def scenario() -> None:
        nonlocal payload
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _FEED
            return httpx.Response(200, content=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("sotetsu",), client=client)
            assert tracker.lines[0].status is LineStatus.UNKNOWN
            await tracker.refresh()
            line = tracker.sotetsu.main
            assert line.status is status
            assert line.line_id == LineId("jp:sotetsu:line_bcfb80c3830e")
            assert line.name == "相鉄線" and line.operator.name == "相模鉄道"
            assert line.provider_id == ProviderId("sotetsu")
            assert line.source_url == "https://www.sotetsu.co.jp/train/status/"
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert line.updated_at is None
            yahoo = tracker.yahoo.get_line(line.line_id)
            assert yahoo is not None and yahoo is not line
            assert yahoo.operator is line.operator and yahoo.status is LineStatus.UNKNOWN
            if status is LineStatus.ALERT:
                alert, = line.alerts
                assert alert.description == json.loads(payload)[0]["MSG"]
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None
                assert tracker.affected_lines == (line,)
            else:
                assert not tracker.alerts and not tracker.affected_lines
            assert not tracker.delay_lines
            payload = normal
            await tracker.refresh()
            assert tracker.sotetsu.main.status is LineStatus.NORMAL
            assert not tracker.alerts and not tracker.affected_lines
            assert line.status is status  # Earlier immutable snapshot remains intact.
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("irregular", "message", "replacement", "status"), [
    (True, "合成：現在の運転見合わせ。", "合成：振替先の案内。", LineStatus.ALERT),
    (True, "合成：明日の計画運休のお知らせ。", "", LineStatus.ALERT),
    (True, "合成：平常に復帰した後のご案内。", "", LineStatus.ALERT),
    (False, "合成：平常状態。", "", LineStatus.NORMAL),
])
def test_synthetic_flags_determine_status_without_prose_inference(
    irregular: bool, message: str, replacement: str, status: LineStatus,
) -> None:
    # Not source evidence; verify the documented boolean mapping and text retention.
    payload = [{"MSG": message, "MSG2": replacement, "IRREGULAR": irregular,
                "E_STATUS": "Suspended", "DATE": "2099/12/31 23:59:59"}]

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload),
        )) as client:
            provider = SotetsuProvider(client=client)
            await provider.refresh()
            assert provider.main.status is status
            assert provider.main.updated_at is None
            assert not provider.active_alerts
            if irregular:
                alert, = provider.unclassified_alerts
                expected = message + ("\n振替輸送：" + replacement if replacement else "")
                assert alert.description == expected
                assert alert.timing is AlertTiming.UNKNOWN
            else:
                assert not provider.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    "not JSON", "{}", "[]", "[null]", '[{"IRREGULAR":false}]',
    '[{"MSG":"test"}]', '[{"MSG":"","IRREGULAR":false}]',
    '[{"MSG":"  ","IRREGULAR":true}]', '[{"MSG":0,"IRREGULAR":false}]',
    '[{"MSG":"test","IRREGULAR":0}]', '[{"MSG":"test","IRREGULAR":"false"}]',
    '[{"MSG":"test","IRREGULAR":null}]',
    '[{"MSG":"test","IRREGULAR":false,"MSG2":null}]',
    '[{"MSG":"test","IRREGULAR":true,"MSG2":7}]',
    '[{"MSG":"one","IRREGULAR":false},{"MSG":"two","IRREGULAR":true}]',
])
def test_synthetic_malformed_payload_preserves_snapshot(payload: str) -> None:
    body = '[{"MSG":"合成：案内。","IRREGULAR":true}]'

    async def scenario() -> None:
        nonlocal body
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=body),
        )) as client:
            provider = SotetsuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            body = payload
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.main.status is LineStatus.ALERT

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_synthetic_fetch_failure_preserves_snapshot_and_tracker_error(failure: str) -> None:
    fail = False
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            if failure == "connection":
                raise httpx.ConnectError("synthetic failure", request=request)
            return httpx.Response(503)
        return httpx.Response(200, json=[{"MSG": "合成：平常。", "IRREGULAR": False}])

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SotetsuProvider(client=client)
            tracker = Tracker(enabled_providers=("sotetsu",), overrides=(provider,))
            assert tracker.sotetsu is provider
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as error:
                await tracker.refresh()
            assert set(error.value.errors) == {ProviderId("sotetsu")}
            assert isinstance(error.value.errors[ProviderId("sotetsu")], FetchError)
            assert tracker.refresh_errors == error.value.errors
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_recovery_clears_notices() -> None:
    irregular = True

    async def scenario() -> None:
        nonlocal irregular
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[{
                "MSG": "合成：テスト状態。", "IRREGULAR": irregular,
            }]),
        )) as client:
            provider = SotetsuProvider(client=client)
            await provider.refresh()
            assert provider.alerts
            irregular = False
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.affected_lines

    asyncio.run(scenario())
