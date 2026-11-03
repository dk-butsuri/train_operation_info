"""Live normal fixture; disruption, recovery and defensive cases are synthetic."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineStatus
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.nagoya_subway import NagoyaSubwayProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_ROUTES = ("H_LINE", "M_LINE", "T_LINE", "S_LINE", "K_LINE")


def _rows() -> list[dict[str, object]]:
    # Synthetic shape matches the live feed; all prose is invented.
    return [dict(
        rosen_id=code, traffic_no=i, slot_no=1, icon_cd="N_T_ICO",
        traffic_title="平常運行", traffic_message="合成の案内本文",
        traffic_section="", traffic_cause="",
    ) for i, code in enumerate(_ROUTES)]


def test_initial_properties_and_canonical_ids() -> None:
    tracker = Tracker(enabled_providers=("nagoya_subway", "yahoo"))
    provider = tracker.nagoya_subway
    assert len(provider.unknown_lines) == 5
    assert provider.delay_lines == provider.affected_lines == ()
    assert provider.alerts == ()
    assert provider.lines == (
        provider.higashiyama, provider.meijo_meiko, provider.tsurumai,
        provider.sakuradori, provider.kamiiida,
    )
    assert "nagoya_subway" in {p.provider_id for p in Tracker().providers}
    for line in provider.lines:
        yahoo_line = tracker.yahoo.get_line(line.line_id)
        assert yahoo_line is not None
        assert yahoo_line.operator == line.operator
        assert yahoo_line is not line
        assert line.fetched_at is None
    assert provider.meijo_meiko.line_id == LineId("jp:operator_f28d789a1fa7:line_205e60be39e6")
    assert provider.meijo_meiko.name == "名古屋市営名城線・名港線"


@pytest.mark.parametrize(("icon", "title", "status", "effect"), [
    ("N_T_ICO", "平常運行", LineStatus.NORMAL, None),
    ("W_T_ICO", "合成の状態", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("E_T_ICO", "合成の状態", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
    ("C_T_ICO", "合成の状態", LineStatus.ALERT, AlertEffect.OTHER),
    ("N_T_ICO", "合成のお知らせ", LineStatus.ALERT, AlertEffect.OTHER),
    ("NEW_ICO", "平常運行", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
])
def test_synthetic_status_codes_and_raw_detail(
    icon: str, title: str, status: LineStatus, effect: AlertEffect | None,
) -> None:
    data = _rows()
    data[0].update(icon_cd=icon, traffic_title=title, traffic_section="合成区間",
                   traffic_cause="合成理由", create_datetime="2099-01-01T10:00:00")
    # Prose mentioning suspension or future dates must never change classification.
    data[0]["traffic_message"] = "運転見合わせは取り消し。明日は運休予定。合成テスト。"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://www.kotsu.city.nagoya.jp/datas/latest_traffic.json"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, json=data)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("nagoya_subway",), client=client)
            before = tracker.nagoya_subway.higashiyama
            await tracker.refresh()
            line = tracker.nagoya_subway.higashiyama
            assert line.status is status
            assert line.source_status == f"{icon}: {title}"
            assert line.updated_at is None
            assert line.fetched_at is not None
            assert line.fetched_at.utcoffset() is not None
            assert before.status is LineStatus.UNKNOWN and before is not line
            assert not client.is_closed
            if effect is None:
                assert line.alerts == ()
            else:
                alert, = line.alerts
                assert alert.title == title
                assert "運転見合わせは取り消し" in alert.description
                assert "区間：合成区間" in alert.description
                assert "理由：合成理由" in alert.description
                assert alert.effect is effect
                assert alert.affected_line_ids == (line.line_id,)
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is alert.active_until is None
                assert tracker.active_alerts == ()
                assert tracker.unclassified_alerts == (alert,)
            assert bool(tracker.delay_lines) == (status is LineStatus.DELAYED)
            assert bool(tracker.unknown_lines) == (status is LineStatus.UNKNOWN)

    asyncio.run(scenario())


def test_synthetic_multiple_slots_recovery_and_bus_exclusion() -> None:
    incident = _rows()
    # Normal slot must not hide the second slot. Bus content is out of scope.
    incident.append(dict(incident[0], slot_no=2, traffic_no=100, icon_cd="E_T_ICO",
                         traffic_title="合成の運行停止"))
    incident.append(dict(incident[0], slot_no=3, traffic_no=101, icon_cd="C_T_ICO",
                         traffic_title="合成の将来案内"))
    incident.append({"rosen_id": "B_LINE", "traffic_title": 123})
    incident[1].update(traffic_message=None, traffic_section="null", traffic_cause=None)
    incident[1].update(icon_cd="C_T_ICO", traffic_title="合成のお知らせ")
    responses = iter([incident, _rows()])

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=next(responses)),
        )) as client:
            provider = NagoyaSubwayProvider(client=client)
            await provider.refresh()
            old = provider.higashiyama
            assert old.status is LineStatus.SUSPENDED
            assert len(old.alerts) == 2
            assert old.alerts[0].alert_id != old.alerts[1].alert_id
            assert provider.meijo_meiko.alerts[0].description == ""
            await provider.refresh()
            assert provider.higashiyama.status is LineStatus.NORMAL
            assert provider.alerts == ()
            assert provider.affected_lines == ()
            assert old.status is LineStatus.SUSPENDED

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "missing_route", "new_route", "duplicate_slot", "duplicate_id", "missing_field",
    "bad_type", "empty_title", "empty_icon", "bad_detail", "non_object", "bad_json", "bad_utf8",
])
def test_synthetic_invalid_response_preserves_complete_snapshot(fault: str) -> None:
    data = _rows()
    if fault == "missing_route":
        data.pop()
    elif fault == "new_route":
        data.append(dict(data[0], rosen_id="NEW_LINE", traffic_no=100))
    elif fault == "duplicate_slot":
        data.append(dict(data[0], traffic_no=100))
    elif fault == "duplicate_id":
        data.append(dict(data[0], slot_no=2))
    elif fault == "missing_field":
        del data[0]["traffic_message"]
    elif fault == "bad_type":
        data[0]["slot_no"] = "1"
    elif fault == "empty_title":
        data[0]["traffic_title"] = "  "
    elif fault == "empty_icon":
        data[0]["icon_cd"] = ""
    elif fault == "bad_detail":
        data[0]["traffic_cause"] = 123
    malformed = json.dumps(data).encode()
    if fault == "non_object":
        malformed = b"[null]"
    elif fault == "bad_json":
        malformed = b"<html>maintenance</html>"
    elif fault == "bad_utf8":
        malformed = b"\xff"
    responses = iter([json.dumps(_rows()).encode(), malformed])

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=next(responses)),
        )) as client:
            provider = NagoyaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "timeout"])
def test_fetch_failure_preserves_snapshot(failure: str) -> None:
    failed = False

    def handler(request: httpx.Request) -> httpx.Response:
        if failed:
            if failure == "http":
                return httpx.Response(503)
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(200, json=_rows())

    async def scenario() -> None:
        nonlocal failed
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NagoyaSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            failed = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_live_normal_fixture_with_utf8_bom() -> None:
    payload = (_FIXTURES / "nagoya_subway_normal.json").read_bytes()
    assert payload.startswith(b"\xef\xbb\xbf")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = NagoyaSubwayProvider(client=client)
            await provider.refresh()
            assert len(provider.lines) == 5
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert provider.alerts == ()
            assert all(line.updated_at is None for line in provider.lines)

    asyncio.run(scenario())
