"""Real official fixtures plus explicitly synthetic malformed/MRT scenarios."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import get_args
from urllib.parse import parse_qs

import httpx
import pytest

from train_operation_info.exceptions import ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, LineId, LineScope, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import SnapshotProvider
from train_operation_info.providers.hankyu import HankyuProvider
from train_operation_info.providers.hanshin import HanshinProvider
from train_operation_info.providers.jrw import JrWestProvider
from train_operation_info.providers.keihan import KeihanProvider
from train_operation_info.providers.singapore_mrt import SingaporeMrtProvider
from train_operation_info.providers.nankai import NankaiProvider
from train_operation_info.providers.osaka_monorail import OsakaMonorailProvider
from train_operation_info import ProviderName, Tracker

_FIXTURES = Path(__file__).parent / "fixtures"


def _provider(name: str, client: httpx.AsyncClient) -> SnapshotProvider:
    if name == "jrw":
        return JrWestProvider(client=client)
    if name == "keihan":
        return KeihanProvider(client=client)
    if name == "hankyu":
        return HankyuProvider(client=client)
    if name == "hanshin":
        return HanshinProvider(client=client)
    if name == "osaka_monorail":
        return OsakaMonorailProvider(client=client)
    if name == "singapore_mrt":
        return SingaporeMrtProvider(client=client)
    if name == "nankai":
        return NankaiProvider(client=client)
    raise ValueError(name)


def _response(name: str, fixture: str, request: httpx.Request) -> httpx.Response:
    if name == "keihan":
        if request.url.path.endswith("info.json"):
            fixture = "keihan_normal.json"
        elif request.url.path.endswith("FileList.xml"):
            fixture = "keihan_filelist.xml"
        else:
            assert request.url.path.endswith("traininfo20261031014631.xml")
    if name == "singapore_mrt":
        if request.method == "GET":
            fixture = "mrt_page.html"
        else:
            assert request.method == "POST"
            assert parse_qs(request.content.decode()) == {"serviceName": ["LTAGOVTrainServiceAlerts"]}
    return httpx.Response(200, content=(_FIXTURES / fixture).read_bytes())


@pytest.mark.parametrize(
    ("name", "fixture", "count", "delayed", "suspended", "partial", "unknown"),
    [
        ("jrw", "jrw_status.json", 61, 1, 0, 0, 0),
        ("jrw", "jrw_api_20261001234249.json", 61, 3, 9, 1, 0),
        ("jrw", "jrw_api_20261021235454.json", 61, 1, 0, 3, 0),
        ("keihan", "keihan_normal.xml", 8, 0, 0, 0, 0),
        ("keihan", "keihan_xml_20230911234517.xml", 8, 0, 3, 0, 0),
        ("keihan", "keihan_xml_20251101104408.xml", 8, 0, 1, 3, 0),
        ("keihan", "keihan_xml_20261013060555.xml", 8, 3, 1, 0, 0),
        ("hankyu", "hankyu_normal.html", 3, 0, 0, 0, 0),
        ("hankyu", "hankyu_20250722023635.html", 3, 1, 0, 0, 0),
        ("hankyu", "hankyu_20230815061839.html", 3, 0, 0, 0, 0),
        ("hanshin", "hanshin_normal.html", 3, 0, 0, 0, 0),
        ("hanshin", "hanshin_20250730092425.html", 3, 0, 0, 0, 0),
        ("hanshin", "hanshin_20240830120316.html", 3, 0, 0, 0, 3),
        ("osaka_monorail", "monorail_normal.html", 2, 0, 0, 0, 0),
        ("singapore_mrt", "mrt_normal.json", 9, 0, 0, 0, 0),
        ("singapore_mrt", "mrt_normal_with_unscoped_message.json", 9, 0, 0, 0, 0),
        ("nankai", "nankai_normal.html", 10, 0, 0, 0, 0),
        ("nankai", "nankai_20250920072018.html", 10, 0, 0, 0, 0),
        ("nankai", "nankai_20250806220111.html", 10, 1, 0, 0, 0),
        ("nankai", "nankai_20261004112434.html", 10, 2, 0, 0, 0),
    ],
)
def test_official_fixtures(
    name: str, fixture: str, count: int, delayed: int, suspended: int, partial: int, unknown: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(name, fixture, request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _provider(name, client)
            await provider.refresh()
            assert len(provider.lines) == count
            assert len({line.line_id for line in provider.lines}) == count
            assert len(provider.delay_lines) == delayed
            assert sum(line.status is LineStatus.SUSPENDED for line in provider.lines) == suspended
            assert sum(line.status is LineStatus.PARTIAL_SUSPENSION for line in provider.lines) == partial
            assert len(provider.unknown_lines) == unknown
            for line in provider.lines:
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                if line.updated_at is not None:
                    assert line.updated_at.utcoffset() is not None
                assert line.line_id in LINE_CATALOG
            if name == "hanshin" and unknown:
                assert len(provider.alerts) == 1
                assert provider.alerts[0].affected_line_ids == ()
            if fixture == "hankyu_20250722023635.html":
                assert provider.delay_lines[0].line_id == LineId("jp:hankyu:kyoto")
                # The body mentions reopening; the actual current icon still says delayed.
                assert "運転再開" in provider.alerts[0].description
            if fixture == "hankyu_20230815061839.html":
                assert all(line.status is LineStatus.ALERT for line in provider.lines)
            if fixture == "keihan_xml_20230911234517.xml":
                # Replacement-transport prose also names Uji and other railways;
                # only XML's direct affected-route fields determine status.
                assert all(line.status is LineStatus.NORMAL for line in provider.lines if line.name == "宇治線")
            if fixture == "jrw_status.json":
                ako = provider.get_line(LineId("jp:jr_west:ako"))
                assert ako is not None and len(ako.alerts) == 1
            if fixture == "mrt_normal_with_unscoped_message.json":
                assert all(line.status is LineStatus.NORMAL for line in provider.lines)
                assert provider.alerts == ()
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("name", ["jrw", "keihan", "hankyu", "hanshin", "osaka_monorail", "singapore_mrt", "nankai"])
def test_malformed_source_never_clears_previous_snapshot(name: str) -> None:
    fixture = {
        "jrw": "jrw_status.json", "keihan": "keihan_normal.xml",
        "hankyu": "hankyu_normal.html", "hanshin": "hanshin_normal.html",
        "osaka_monorail": "monorail_normal.html", "singapore_mrt": "mrt_normal.json",
        "nankai": "nankai_normal.html",
    }[name]
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            return httpx.Response(200, text="<html>Maintenance</html>")
        return _response(name, fixture, request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _provider(name, client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_jrw_rejects_naive_source_timestamp() -> None:
    text = (_FIXTURES / "jrw_status.json").read_text(encoding="utf-8").replace("+09:00", "", 1)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=text),
        )) as client:
            provider = JrWestProvider(client=client)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert len(provider.unknown_lines) == 61

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("payload", "expected", "unscoped"),
    [
        ('{"value":{"Status":1,"AffectedSegments":[],"Message":[]}}', LineStatus.NORMAL, False),
        ('{"value":{"Status":2,"AffectedSegments":[],"Message":[{"Content":"07:30-EWL-Minor Delay","CreatedDate":"2026-11-01T07:30:00"}]}}', LineStatus.ALERT, False),
        ('{"value":{"Status":2,"AffectedSegments":[],"Message":[{"Content":"07:30-EWL-Major No train service between two stations","CreatedDate":"2026-11-01T07:30:00+08:00"}]}}', LineStatus.ALERT, False),
        ('{"value":{"Status":1,"AffectedSegments":[],"Message":[{"Content":"07:30-EWL-Planned early closure"}]}}', LineStatus.ALERT, False),
        ('{"value":{"Status":2,"AffectedSegments":[{"Line":"EWL","Stations":"EW1;EW2"}],"Message":[]}}', LineStatus.UNKNOWN, False),
        ('{"value":{"Status":2,"AffectedSegments":[],"Message":[{"Content":"07:30-EWL-NewCategory"}]}}', LineStatus.UNKNOWN, True),
        # A newer unsupported Normal header must not establish recovery.
        ('{"value":{"Status":1,"AffectedSegments":[],"Message":[{"Content":"08:00-EWL-Normal service resumed","CreatedDate":"2026-11-01T08:00:00+08:00"},{"Content":"07:30-EWL-Major No train service","CreatedDate":"2026-11-01T07:30:00+08:00"}]}}', LineStatus.UNKNOWN, True),
    ],
)
def test_synthetic_singapore_mrt_alerts_and_recovery(
    payload: str, expected: LineStatus, unscoped: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, text=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            await provider.refresh()
            assert provider.provider_id == ProviderId("singapore_mrt")
            assert provider.metadata.provider_id == provider.provider_id
            assert all(line.provider_id == provider.provider_id for line in provider.lines)
            assert all(line.line_id.startswith("sg:mrt:") for line in provider.lines)
            line = provider.east_west
            assert line.status is expected
            assert provider.north_south.status is (LineStatus.UNKNOWN if unscoped else LineStatus.NORMAL)
            if line.updated_at is not None:
                assert line.updated_at.utcoffset() == timedelta(hours=8)
            assert line.operator.name == "SMRT Trains"
            assert provider.downtown.operator.name == "SBS Transit"
            if expected is LineStatus.NORMAL:
                assert line.alerts == ()

    asyncio.run(scenario())


@pytest.mark.parametrize(("content", "expected", "unscoped"), [
    ("12:00-EWL-Minor. Additional travelling time of 10 minutes. NSL has no train service disruption.", LineStatus.ALERT, False),
    ("12:00-EWL-Major. No train service between two stations.", LineStatus.ALERT, False),
    ("Service on NSL has resumed; please use EWL alternatives.", LineStatus.UNKNOWN, True),
])
def test_singapore_prose_never_establishes_severity_scope_or_recovery(
    content: str, expected: LineStatus, unscoped: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, json={
            "value": {"Status": 2, "AffectedSegments": [], "Message": [{"Content": content}]},
        })

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            await provider.refresh()
            assert provider.east_west.status is expected
            assert provider.north_south.status is (LineStatus.UNKNOWN if unscoped else LineStatus.NORMAL)
            alert, = provider.east_west.alerts
            assert alert.description == content
            assert alert.affected_line_ids == (() if unscoped else (provider.east_west.line_id,))
            assert not provider.delay_lines
    asyncio.run(scenario())


def test_singapore_empty_normal_feed_clears_old_notice() -> None:
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, json={"value": {
            "Status": 1 if recovered else 2, "AffectedSegments": [],
            "Message": [] if recovered else [{"Content": "12:00-EWL-Major. Service disruption."}],
        }})

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            await provider.refresh()
            assert provider.east_west.status is LineStatus.ALERT
            assert provider.east_west.alerts
            recovered = True
            await provider.refresh()
            current = provider.get_line(provider.east_west.line_id)
            assert current is not None and current.status is LineStatus.NORMAL
            assert not provider.alerts
    asyncio.run(scenario())


@pytest.mark.parametrize(("status", "segment", "message", "expected"), [
    (1, False, "07:30-EWL-Minor Delay", LineStatus.ALERT),
    (1, False, "07:30-EWL-NewCategory", LineStatus.UNKNOWN),
    (1, True, None, LineStatus.UNKNOWN),
    (1, False, "Bus diversion near EWL; no rail alert", LineStatus.NORMAL),
    (2, False, None, LineStatus.UNKNOWN),
])
def test_synthetic_singapore_mrt_mixed_feed(
    status: int, segment: bool, message: str | None, expected: LineStatus,
) -> None:
    # Start with the actual bus-only response; the modifications below are synthetic.
    payload = json.loads((_FIXTURES / "mrt_normal_with_unscoped_message.json").read_bytes())
    payload["value"]["Status"] = status
    if segment:
        payload["value"]["AffectedSegments"] = [{"Line": "EWL", "Stations": "EW1;EW2"}]
    if message is not None:
        payload["value"]["Message"].append({"Content": message})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            await provider.refresh()
            assert provider.east_west.status is expected
            if status == 1:
                unscoped = message == "07:30-EWL-NewCategory"
                assert all(
                    line.status is (LineStatus.UNKNOWN if unscoped else LineStatus.NORMAL)
                    for line in provider.lines if line is not provider.east_west
                )
                assert all("Bus" not in alert.description for alert in provider.alerts)
            else:
                # An unscoped message must not hide an explicit network disruption.
                assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
                alert, = provider.alerts
                assert alert.affected_line_ids == ()
                assert alert.description == payload["value"]["Message"][0]["Content"]

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    '{}',
    '{"value":{"Status":"1","AffectedSegments":[],"Message":[]}}',
    '{"value":{"Status":99,"AffectedSegments":[],"Message":[]}}',
    '{"value":{"Status":2,"AffectedSegments":[],"Message":[]}}',
    '{"value":{"Status":2,"AffectedSegments":[{"Line":"UNRECOGNIZED"}],"Message":[]}}',
])
def test_singapore_mrt_invalid_json_is_not_normal(payload: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, text=payload)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert len(provider.unknown_lines) == 9

    asyncio.run(scenario())


def test_singapore_mrt_selection_injection_and_error_identity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=(_FIXTURES / "mrt_page.html").read_bytes())
        return httpx.Response(200, text="invalid JSON")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SingaporeMrtProvider(client=client)
            tracker = Tracker(enabled_providers=("singapore_mrt",), overrides=(provider,))
            assert tracker.singapore_mrt is provider
            assert tracker.providers == (provider,)
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("singapore_mrt")}
            assert isinstance(captured.value.errors[ProviderId("singapore_mrt")], ParseError)
            assert set(tracker.refresh_errors) == {ProviderId("singapore_mrt")}

    asyncio.run(scenario())


def test_tracker_finishes_other_providers_when_one_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "trafficinfo.westjr.co.jp":
            return httpx.Response(503)
        return _response("hankyu", "hankyu_normal.html", request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("jrw", "hankyu"), client=client)
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("jrw")}
            assert set(tracker.refresh_errors) == {ProviderId("jrw")}
            assert tracker.hankyu.kyoto.status is LineStatus.NORMAL
            assert tracker.jrw.osaka_loop.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


def test_canonical_ids_are_reused_without_sharing_source_state() -> None:
    tracker = Tracker()
    # Include every opt-in source when checking canonical coverage.
    all_sources = Tracker(enabled_providers=get_args(ProviderName))
    assert {line.line_id for line in all_sources.lines} == set(LINE_CATALOG)
    assert len(tracker.unknown_lines) == len(tracker.lines)
    assert len(tracker.nankai.lines) == 10
    assert tracker.jrw.ako_kinki is tracker.jrw.ako_okayama
    assert tracker.hankyu.kobe.scope is LineScope.GROUP
    assert tracker.jrw.kobe.scope is LineScope.LINE
    definition = LINE_CATALOG[LineId("jp:osaka_metro:midosuji")]
    other = definition.create_line(ProviderId("another_source"), "https://example.com/")
    official = tracker.osaka_metro.midosuji
    assert official is not other
    assert official.line_id == other.line_id
    assert official.operator is other.operator
    assert official.provider_id != other.provider_id


def test_every_provider_has_reviewed_typed_metadata() -> None:
    for provider in Tracker().providers:
        metadata = provider.metadata
        assert metadata.provider_id == provider.provider_id
        assert str(metadata.source_page_url).startswith("https://")
        if provider.provider_id in (
            ProviderId("rinkai"), ProviderId("jrkyushu"), ProviderId("metro_trains_melbourne"),
            ProviderId("tosakuro"),
        ):
            # General website terms were not found. Conditions for separate
            # services do not establish a general terms URL for these feeds.
            assert metadata.terms_url is None
            assert metadata.usage_permission is UsagePermission.UNSPECIFIED
            if provider.provider_id != ProviderId("metro_trains_melbourne"):
                assert metadata.additional_terms_urls
        else:
            assert metadata.terms_url is not None
        assert metadata.reviewed_at.utcoffset() is not None
        assert isinstance(metadata.usage_permission, UsagePermission)
        assert metadata.usage_note
    # Model-level enforcement applies to metadata and every Line timestamp too.
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        metadata.model_validate({**metadata.model_dump(), "reviewed_at": datetime(2026, 11, 1)})
    assert datetime.now(timezone.utc).utcoffset() == timedelta(0)
