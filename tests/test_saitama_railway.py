"""Live normal evidence; explicit synthetic cases for the public JS contract."""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertTiming, LineId, LineStatus, ProviderId
from train_operation_info.providers.saitama_railway import SaitamaRailwayProvider
from train_operation_info.snapshots import SnapshotReplayTransport

_FEED = "https://www.s-rail.co.jp/service_status/status.json"
_FIXTURES = Path(__file__).parent / "fixtures"


def _message(
    label: str = "遅延", *, kind: str = "message", latest: bool = True,
    text: str = "合成：本文中の運休・復旧・将来の日付は分類に使わない。",
    time: str = "20261104123456",
) -> dict[str, object]:
    return {"type": kind, "latest": latest, "time": time,
            "langs": {"ja": {"status": label, "text": text}}}


def test_live_normal_and_shared_catalog_identity() -> None:
    body = (_FIXTURES / "saitama_railway_normal.json").read_bytes()

    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _FEED and request.method == "GET"
            return httpx.Response(200, content=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("saitama_railway",), client=client)
            assert tracker.saitama_railway.main.status is LineStatus.UNKNOWN
            await tracker.refresh()
            line = tracker.saitama_railway.main
            assert line.status is LineStatus.NORMAL
            assert line.line_id == LineId("jp:operator_6792d0f7efc4:line_1b9213f482b7")
            assert line.name == "埼玉高速鉄道線" and line.operator.name == "埼玉高速鉄道"
            assert line.provider_id == ProviderId("saitama_railway")
            assert line.updated_at == datetime.fromisoformat("2026-10-29T04:00:03+09:00")
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert not line.alerts and not tracker.affected_lines
            yahoo = tracker.yahoo.get_line(line.line_id)
            assert yahoo is not None and yahoo is not line
            assert yahoo.operator is line.operator and yahoo.status is LineStatus.UNKNOWN
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "status"), [
    ("平常運転", LineStatus.NORMAL), ("遅延", LineStatus.DELAYED),
    ("運転見合わせ", LineStatus.SUSPENDED), ("運休", LineStatus.SUSPENDED),
    ("一部運休", LineStatus.PARTIAL_SUSPENSION),
    ("運転再開見込", LineStatus.ALERT), ("お知らせ", LineStatus.ALERT),
    ("運転再開", LineStatus.ALERT), ("直通運転中止", LineStatus.ALERT),
    ("折返し運転", LineStatus.ALERT), ("経路変更", LineStatus.ALERT),
    ("直通運転再開", LineStatus.ALERT), ("バス代行", LineStatus.ALERT),
    ("振替輸送", LineStatus.ALERT), ("リフレッシュ工事", LineStatus.ALERT),
    ("一部運転再開", LineStatus.ALERT), ("未知の状態", LineStatus.UNKNOWN),
    ("遅延のお知らせ", LineStatus.UNKNOWN),
])
def test_synthetic_dedicated_status_does_not_classify_prose(label: str, status: LineStatus) -> None:
    message = _message(label)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"messages": [message]}),
        )) as client:
            provider = SaitamaRailwayProvider(client=client)
            await provider.refresh()
            assert provider.main.status is status
            assert provider.main.source_status == label
            assert provider.main.updated_at == datetime.fromisoformat("2026-11-04T12:34:56+09:00")
            assert not provider.active_alerts
            if status is LineStatus.NORMAL:
                assert not provider.alerts
            else:
                alert, = provider.unclassified_alerts
                assert alert.title == label
                assert alert.description == "合成：本文中の運休・復旧・将来の日付は分類に使わない。"
                assert alert.affected_line_ids == (provider.main.line_id,)
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["overtime", "new-type"])
def test_synthetic_unknown_type_preserves_notice(kind: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"messages": [_message("", kind=kind)]}),
        )) as client:
            provider = SaitamaRailwayProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.alerts[0].title == kind
            assert provider.alerts[0].description.startswith("合成：")

    asyncio.run(scenario())


def test_synthetic_latest_selection_multiple_notices_and_recovery() -> None:
    messages = [_message("運転見合わせ", latest=False),
                _message("遅延"), _message("直通運転中止", time="20261104123500")]

    async def scenario() -> None:
        nonlocal messages
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"messages": messages,
                                                    "time": "20990101000000", "created": "ignored"}),
        )) as client:
            provider = SaitamaRailwayProvider(client=client)
            await provider.refresh()
            previous = provider.main
            assert previous.status is LineStatus.DELAYED
            assert len(provider.alerts) == 2
            assert previous.updated_at == datetime.fromisoformat("2026-11-04T12:35:00+09:00")
            messages = [_message(kind="stdtxt"), _message("運転見合わせ", latest=False)]
            await provider.refresh()
            restored = provider.main
            assert restored.status is LineStatus.NORMAL and not restored.alerts
            assert previous.status is LineStatus.DELAYED and len(previous.alerts) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("messages", [[], [{"latest": False}], [{}]])
def test_synthetic_empty_or_history_only_is_unknown(messages: list[dict[str, object]]) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"messages": messages}),
        )) as client:
            provider = SaitamaRailwayProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.main.updated_at is None and not provider.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    "not json", "null", "[]", "{}", '{"messages":null}', '{"messages":[null]}',
    '{"messages":[{"latest":1}]}', '{"messages":[{"latest":"false"}]}',
    '{"messages":[{"latest":null}]}', '{"messages":[{"latest":true}]}',
    json.dumps({"messages": [_message(time="20260230000000")]}),
    json.dumps({"messages": [_message(time="20261104")]}),
    json.dumps({"messages": [_message("")]}),
    json.dumps({"messages": [_message(text=" ")]}),
    json.dumps({"messages": [{**_message(), "langs": {"en": {"text": "synthetic"}}}]}),
    json.dumps({"messages": [{**_message(), "time": 20261104123456}]}),
    json.dumps({"messages": [{**_message(), "langs": {"ja": {"text": 123, "status": "遅延"}}}]}),
])
def test_synthetic_invalid_current_data_keeps_previous_snapshot(payload: str) -> None:
    body = json.dumps({"messages": [_message()]})

    async def scenario() -> None:
        nonlocal body
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=body),
        )) as client:
            provider = SaitamaRailwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            body = payload
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "connection"])
def test_synthetic_fetch_failure_is_reported_without_losing_state(failure: str) -> None:
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            if failure == "connection":
                raise httpx.ConnectError("synthetic failure", request=request)
            return httpx.Response(503)
        return httpx.Response(200, json={"messages": [_message()]})

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SaitamaRailwayProvider(client=client)
            tracker = Tracker(enabled_providers=("saitama_railway",), overrides=(provider,))
            assert tracker.saitama_railway is provider
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as error:
                await tracker.refresh()
            assert isinstance(error.value.errors[ProviderId("saitama_railway")], FetchError)
            assert tracker.refresh_errors == error.value.errors
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_recording_replays_all_current_notices(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"messages": [
                _message("運転見合わせ", latest=False), _message("一部運休"),
                _message("お知らせ"),
            ]}),
        )) as client:
            provider = SaitamaRailwayProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            expected = provider.lines
        capture, = (tmp_path / "saitama_railway").glob("[0-9]*/*.json")
        async with httpx.AsyncClient(transport=SnapshotReplayTransport(capture)) as client:
            replay = SaitamaRailwayProvider(client=client)
            await replay.refresh()
            assert replay.lines == expected

    asyncio.run(scenario())
