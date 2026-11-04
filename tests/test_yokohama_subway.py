"""Official empty list/history evidence; current incidents and recovery are synthetic."""

import asyncio
from datetime import timedelta
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.yokohama_subway import YokohamaSubwayProvider
from train_operation_info.snapshots import SnapshotReplayTransport

_FIXTURES = Path(__file__).parent / "fixtures"
_FEED = "https://cms.yokohama-operation.cld.navitime.jp/api/web/railroad/operations?lang=ja"
_NOW = "2026-11-04T21:51:08+09:00"


def _notice(
    group: str = "synthetic-1", route: str = "1", code: str = "2", label: str = "遅延",
) -> dict[str, object]:
    return {
        "operationGroupId": group,
        "line": {"id": route, "name": "ブルーライン" if route == "1" else "グリーンライン"},
        "icon": "warning", "hasDelayStatus": True,
        "period": {"begin": "2026-11-04T20:00:00+09:00", "end": None},
        "sections": ["合成区間"], "cause": "合成：明日は運休。遅延は解消しました。",
        "maxDelayTime": "合成10分", "operationStatus": {
            "id": code, "name": label, "updateTime": "2026-11-04T20:10:00+09:00",
        },
    }


def _feed(*items: dict[str, object]) -> bytes:
    return json.dumps({"now": _NOW, "items": items}, ensure_ascii=False).encode()


def test_official_empty_list_identity_and_independent_yahoo_snapshot() -> None:
    payload = (_FIXTURES / "yokohama_subway_normal.json").read_bytes()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert str(request.url) == _FEED
        assert request.method == "GET" and request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YokohamaSubwayProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not requests and len(provider.unknown_lines) == 2
            tracker = Tracker(enabled_providers=("yokohama_subway",), overrides=(provider,))
            await tracker.refresh()
            assert requests == [_FEED]
            assert provider.lines == (provider.blue, provider.green)
            for line in provider.lines:
                assert line.status is LineStatus.NORMAL and not line.alerts
                assert line.source_line_names == (line.name,) and line.source_status == "平常運行"
                assert line.operator.name == "横浜市交通局"
                assert line.updated_at is None and line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo is not line and yahoo.operator == line.operator
                assert yahoo.status is LineStatus.UNKNOWN
            assert not client.is_closed
            assert provider.metadata.usage_permission is UsagePermission.UNSPECIFIED
        assert ProviderId("yokohama_subway") in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())


def test_official_history_records_in_explicitly_synthetic_current_envelope() -> None:
    history = json.loads((_FIXTURES / "yokohama_subway_history.json").read_bytes())
    payload = json.dumps({"now": _NOW, "items": history["items"]}).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = YokohamaSubwayProvider(client=client)
            await provider.refresh()
            assert provider.blue.status is LineStatus.DELAYED
            assert provider.green.status is LineStatus.NORMAL
            assert len(provider.alerts) == 7
            for alert, original in zip(provider.alerts, history["items"]):
                assert alert.effect is AlertEffect.DELAYS
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.affected_line_ids == (provider.blue.line_id,)
                assert alert.active_from is None and alert.active_until is None
                assert json.loads(alert.description) == original
            assert not provider.active_alerts and provider.blue.updated_at is None

    asyncio.run(scenario())


@pytest.mark.parametrize(("code", "label", "expected"), [
    ("2", "遅延", LineStatus.DELAYED),
    ("new", "遅延", LineStatus.UNKNOWN),
    ("2", "合成：遅延はありません", LineStatus.UNKNOWN),
    ("new", "運転見合わせ", LineStatus.UNKNOWN),
    ("new", "平常運行", LineStatus.UNKNOWN),
])
def test_synthetic_status_does_not_follow_prose_and_recovery_clears_notices(
    code: str, label: str, expected: LineStatus,
) -> None:
    payload = _feed(_notice(route="2", code=code, label=label))

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            tracker = Tracker(enabled_providers=("yokohama_subway",), client=client)
            await tracker.refresh()
            provider = tracker.yokohama_subway
            assert provider.blue.status is LineStatus.NORMAL and provider.green.status is expected
            alert, = tracker.alerts
            assert alert.affected_line_ids == (provider.green.line_id,)
            assert alert.timing is AlertTiming.UNKNOWN
            assert "明日は運休" in alert.description and "遅延は解消" in alert.description
            assert alert.active_from is None and alert.active_until is None
            assert provider.green.updated_at is None
            payload = _feed()
            await tracker.refresh()
            assert not tracker.alerts and not tracker.unknown_lines and not tracker.affected_lines

    asyncio.run(scenario())


def test_synthetic_multiple_notices_preserve_unknown_and_all_records() -> None:
    payload = _feed(_notice(), _notice(group="synthetic-2", code="new", label="合成：長期案内"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = YokohamaSubwayProvider(client=client)
            await provider.refresh()
            assert provider.blue.status is LineStatus.UNKNOWN and len(provider.blue.alerts) == 2
            assert provider.green.status is LineStatus.NORMAL
            assert "長期案内" in provider.blue.alerts[1].description
            assert len({a.alert_id for a in provider.alerts}) == 2

    asyncio.run(scenario())


def test_synthetic_incident_record_replay_preserves_notices_and_fetch_time(tmp_path: Path) -> None:
    # The official UI keys groups inside each route's separately filtered list.
    payload = _feed(_notice(), _notice(route="2", code="new", label="合成案内"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = YokohamaSubwayProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            original = provider.lines
            assert len(provider.alerts) == 2
        capture, = tmp_path.glob("yokohama_subway/[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture)
        assert len(transport.capture.responses) == 1
        async with httpx.AsyncClient(transport=transport) as client:
            replay = YokohamaSubwayProvider(client=client)
            await replay.refresh()
            assert replay.lines == original

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", [
    b"{}", b"[]", b"not json", b'{"now":"2026-11-04T21:00:00","items":[]}',
    b'{"now":"2026-11-04T21:00:00+09:00","items":null}',
    _feed(_notice(), _notice()),
    _feed({**_notice(), "line": {"id": "3", "name": "未知線"}}),
    _feed({**_notice(), "line": {"id": "1", "name": "グリーンライン"}}),
    _feed({**_notice(), "operationGroupId": ""}),
    _feed({**_notice(), "operationStatus": {"id": "2", "name": "遅延"}}),
    _feed({**_notice(), "operationStatus": {"id": 2, "name": "遅延", "updateTime": _NOW}}),
    _feed({**_notice(), "sections": "合成区間"}),
    _feed({**_notice(), "hasDelayStatus": "true"}),
    _feed({**_notice(), "period": {"begin": _NOW, "end": "2026-11-03T00:00:00+09:00"}}),
    _feed({k: v for k, v in _notice().items() if k != "operationStatus"}),
])
def test_synthetic_invalid_data_keeps_both_route_snapshots(broken: bytes) -> None:
    payload = _feed(_notice())

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            tracker = Tracker(enabled_providers=("yokohama_subway",), client=client)
            await tracker.refresh()
            previous = tracker.yokohama_subway.lines
            payload = broken
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert isinstance(captured.value.errors[ProviderId("yokohama_subway")], ParseError)
            assert tracker.yokohama_subway.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("network", [False, True])
def test_synthetic_fetch_failures_keep_snapshot(network: bool) -> None:
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        if fail and network:
            raise httpx.ConnectError("synthetic failure", request=request)
        return httpx.Response(503 if fail else 200, content=_feed(_notice()))

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YokohamaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())
