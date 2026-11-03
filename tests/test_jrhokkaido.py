"""Real area_02/03/04/05 captures; incidents besides soya and mutations are synthetic."""

import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertTiming, LineId, LineScope, LineStatus, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.jrhokkaido import JrHokkaidoProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_AREAS = ("02", "03", "04", "05")


def _raw(area: str) -> bytes:
    return (_FIXTURES / f"jrhokkaido_area_{area}.json").read_bytes()


def _default_bodies() -> dict[str, bytes]:
    return {area: _raw(area) for area in _AREAS}


def _response(bodies: dict[str, bytes], request: httpx.Request) -> httpx.Response:
    assert request.url.host == "www3.jrhokkaido.co.jp"
    assert request.method == "GET"
    assert request.headers["User-Agent"] == USER_AGENT
    area = request.url.path.rsplit("/", 1)[-1].removeprefix("area_").removesuffix(".json")
    return httpx.Response(200, content=bodies[area])


def test_real_capture_has_one_genuine_soya_suspension_and_rest_normal() -> None:
    bodies = _default_bodies()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _response(bodies, request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("jrhokkaido",), client=client)
            provider = tracker.jrhokkaido
            assert len(provider.unknown_lines) == 14
            await tracker.refresh()
            assert calls == [
                "/webunkou/json/area/area_02.json",
                "/webunkou/json/area/area_03.json",
                "/webunkou/json/area/area_04.json",
                "/webunkou/json/area/area_05.json",
            ]
            assert len(provider.lines) == 14
            soya = provider.soya
            assert soya.status is LineStatus.ALERT
            assert soya.scope is LineScope.LINE
            assert len(soya.alerts) == 1
            alert = soya.alerts[0]
            assert "熊" in alert.description
            assert "宗谷線" in alert.description or "宗谷" in alert.title
            assert alert.affected_line_ids == ()
            assert alert.timing is AlertTiming.UNKNOWN
            assert alert.active_from is None and alert.active_until is None
            assert soya.updated_at == datetime.fromisoformat("2026-11-02T15:39:00+09:00")
            others = [line for line in provider.lines if line.line_id != soya.line_id]
            assert all(line.status is LineStatus.NORMAL for line in others)
            assert all(not line.alerts and line.updated_at is None for line in others)
            group_lines = [line for line in provider.lines if line.scope is LineScope.GROUP]
            line_lines = [line for line in provider.lines if line.scope is LineScope.LINE]
            assert len(group_lines) == 6 and len(line_lines) == 8
            assert all(line.operator.name == "JR北海道" for line in provider.lines)
            assert all(line.source_url.startswith("https://www3.jrhokkaido.co.jp/webunkou/senku.html?id=")
                       for line in provider.lines)
            assert all(line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                       for line in provider.lines)
            assert provider.gakuen_toshi.source_line_names == ("学園都市線",)
            assert provider.hanasaki.source_line_names == ("根室線（花咲線）",)
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert provider.metadata.terms_url is not None

    asyncio.run(scenario())


def test_synthetic_unknown_code_outside_service_hours() -> None:
    bodies = _default_bodies()
    bodies["02"] = bodies["02"].replace(b'"gakuen":0', b'"gakuen":2', 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: _response(bodies, r),
        )) as client:
            provider = JrHokkaidoProvider(client=client)
            await provider.refresh()
            line = provider.gakuen_toshi
            assert line.status is LineStatus.UNKNOWN
            assert line.source_status == "2"
            assert len(line.alerts) == 1
            assert "status=2" in line.alerts[0].description
            assert line.alerts[0].affected_line_ids == (line.line_id,)
            # An unrelated normal line sharing the same response is unaffected.
            assert provider.hidaka.status is LineStatus.NORMAL

    asyncio.run(scenario())


def test_synthetic_group_alert_without_matching_notice_falls_back_to_fixed_remark() -> None:
    bodies = _default_bodies()
    # hakodate_line (GROUP) alert in area_03, whose gaikyo[0] is the empty
    # "no notice" placeholder (title/time == "") rather than a real notice.
    bodies["03"] = bodies["03"].replace(b'"hakodate":0', b'"hakodate":1', 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: _response(bodies, r),
        )) as client:
            provider = JrHokkaidoProvider(client=client)
            await provider.refresh()
            line = provider.hakodate_line
            assert line.scope is LineScope.GROUP
            assert line.status is LineStatus.ALERT
            assert len(line.alerts) == 1
            assert line.alerts[0].description == "運休・３０分以上の遅延・運転見合わせが発生"
            assert line.alerts[0].affected_line_ids == ()
            assert line.updated_at is None

    asyncio.run(scenario())


def test_synthetic_recovery_clears_alert_and_updated_at() -> None:
    incident = _default_bodies()
    recovered = dict(incident)
    recovered["04"] = incident["04"].replace(b'"soya":1', b'"soya":0', 1)
    current = incident

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(current, request)

    async def scenario() -> None:
        nonlocal current
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrHokkaidoProvider(client=client)
            await provider.refresh()
            soya = provider.soya
            assert soya.status is LineStatus.ALERT and soya.updated_at is not None
            current = recovered
            await provider.refresh()
            soya = provider.soya
            assert soya.status is LineStatus.NORMAL
            assert not soya.alerts and soya.updated_at is None
            assert not provider.alerts and not provider.affected_lines

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", [
    "http", "extra_field", "missing_field", "wrong_type", "bad_notice_time",
    "bad_notice_date", "missing_eikyo_field",
])
def test_synthetic_failure_preserves_entire_snapshot(kind: str) -> None:
    original = _default_bodies()
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not broken:
            return _response(original, request)
        if kind == "http":
            return httpx.Response(503)
        mutated = dict(original)
        body = original["04"]
        if kind == "extra_field":
            body = body.replace(b'"rumoi":0,"senmo"', b'"rumoi":0,"extraField":0,"senmo"', 1)
        elif kind == "missing_field":
            body = body.replace(b'"hidaka":0,"soya"', b'"soya"', 1)
        elif kind == "wrong_type":
            body = body.replace(b'"soya":1,"sekihoku"', b'"soya":"1","sekihoku"', 1)
        elif kind == "bad_notice_time":
            body = body.replace(
                '"time":"2026年11月02日 15時39分現在"'.encode(), b'"time":"not a time"', 1,
            )
        elif kind == "bad_notice_date":
            body = body.replace(
                '"time":"2026年11月02日 15時39分現在"'.encode(),
                '"time":"2026年02月30日 10時00分現在"'.encode(), 1,
            )
        elif kind == "missing_eikyo_field":
            body = body.replace(
                b'"eikyo":{"spo":1,"doo":1,"donan":0,"dohoku":1,"doto":0}',
                b'"eikyo":{"spo":1,"doo":1,"donan":0,"doto":0}', 1,
            )
        mutated["04"] = body
        return _response(mutated, request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrHokkaidoProvider(client=client)
            await provider.refresh()
            before = provider.lines
            broken = True
            with pytest.raises(FetchError if kind == "http" else ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_tracker_injection_selection_and_other_provider_failure() -> None:
    bodies = _default_bodies()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return _response(bodies, request) if request.url.host == "www3.jrhokkaido.co.jp" else httpx.Response(503)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrHokkaidoProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert calls == [] and disabled.jrhokkaido is provider
            assert "jrhokkaido" in {p.provider_id for p in Tracker().providers}
            tracker = Tracker(enabled_providers=("jrhokkaido", "jrw"), overrides=(provider,), client=client)
            with pytest.raises(RefreshError) as caught:
                await tracker.refresh()
            assert set(caught.value.errors) == {"jrw"}
            assert not provider.unknown_lines and tracker.jrhokkaido is provider

    asyncio.run(scenario())


def test_canonical_ids_are_reused_for_the_eight_single_line_senku() -> None:
    provider = JrHokkaidoProvider()
    expected = {
        "gakuen_toshi": "jp:jr_hokkaido:line_1b3f7157a97f",
        "hidaka": "jp:jr_hokkaido:line_d2d4151ea5a8",
        "soya": "jp:jr_hokkaido:line_d3463a409618",
        "sekihoku": "jp:jr_hokkaido:line_903b6ae2bcf1",
        "furano": "jp:jr_hokkaido:line_ea3437497425",
        "sekisho": "jp:jr_hokkaido:line_6664f6717ccf",
        "hanasaki": "jp:jr_hokkaido:line_0ec04639e5c5",
        "senmo": "jp:jr_hokkaido:line_e15dbba9f742",
    }
    for attribute, line_id in expected.items():
        line = getattr(provider, attribute)
        assert line.line_id == LineId(line_id)
        assert line.scope is LineScope.LINE
    for attribute in ("airport", "hakodate_chitose", "muroran", "hakodate_liner", "hakodate_line", "nemuro"):
        line = getattr(provider, attribute)
        assert line.scope is LineScope.GROUP
        assert line.line_id.startswith("jp:jr_hokkaido:") and line.line_id.endswith("_group")


def test_saved_evidence_hashes() -> None:
    manifest = json.loads((_FIXTURES / "jrhokkaido_manifest.json").read_text(encoding="utf-8"))
    for record in manifest:
        assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record["fixture_sha256"]
        assert record["fixture_sha256"] == record["original_sha256"]
