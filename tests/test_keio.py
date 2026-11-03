"""Live official normal XML and a real archived incident; other mutations are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, LineId, LineStatus, ProviderId, UsagePermission,
)
from train_operation_info.providers.keio import KeioProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.keio.co.jp/_system/_unkou/unkouInformation.xml"
_LINE_IDS = (
    LineId("jp:keio:line_0cb7d2efef5d"), LineId("jp:keio:line_3c2563f11b2a"),
    LineId("jp:keio:line_25cd0e31969a"), LineId("jp:keio:line_5e6de121e906"),
    LineId("jp:keio:line_d155e8d8cfa8"), LineId("jp:keio:line_da0cc13de9db"),
    LineId("jp:keio:line_1690db7527c8"),
)


def _response(name: str) -> httpx.Response:
    return httpx.Response(200, content=(_FIXTURES / name).read_bytes())


def test_official_normal_and_canonical_ids() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response("keio_normal.xml"),
        )) as client:
            provider = KeioProvider(client=client)
            tracker = Tracker(enabled_providers=("keio",), overrides=(provider,))
            assert tracker.providers == (provider,)
            assert len(tracker.unknown_lines) == 7
            await tracker.refresh()
            assert len(tracker.lines) == 7
            assert {line.line_id for line in provider.lines} == set(_LINE_IDS)
            assert all(line.status is LineStatus.NORMAL for line in tracker.lines)
            assert not tracker.alerts and not tracker.affected_lines
            assert provider.lines == (
                provider.main, provider.shinsen, provider.sagamihara, provider.takao,
                provider.keibajo, provider.doubutsuen, provider.inokashira,
            )
            for line in provider.lines:
                assert line.operator.name == "京王電鉄"
                assert line.provider_id == ProviderId("keio")
                assert line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                assert line.updated_at is not None
                assert line.updated_at.utcoffset() == timedelta(hours=9)
            assert "平常通り運転しています" in (provider.main.source_status or "")
            assert provider.metadata.provider_id == ProviderId("keio")
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert not client.is_closed

    asyncio.run(scenario())


def test_real_archived_incident_marks_every_line_unknown_then_recovers() -> None:
    # Transcoded to UTF-8 from the genuine 2019-09-09 Wayback capture of the
    # XML (originally Shift_JIS); see tests/fixtures/KEIO.md. Content is
    # unmodified aside from the encoding. The free text names only the
    # Inokashira Line, not the whole network the normal sentence names.
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        return _response("keio_normal.xml" if recovered else "keio_20190909043234_utf8.xml")

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeioProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            alert, = provider.alerts
            assert alert.affected_line_ids == ()
            assert alert.effect is AlertEffect.UNKNOWN
            assert "井の頭線" in alert.description and "見合せ" in alert.description
            assert all(line.alerts == (alert,) for line in provider.lines)
            assert provider.inokashira.updated_at is not None
            assert provider.inokashira.updated_at.isoformat() == "2019-09-09T13:30:00+09:00"
            # Recovery: the next normal feed clears every line and the alert.
            recovered = True
            await provider.refresh()
            assert not provider.alerts
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)

    asyncio.run(scenario())


def test_shift_jis_declared_xml_is_a_parse_error_not_a_crash() -> None:
    # The genuine archived Shift_JIS bytes: CPython's expat-backed
    # xml.etree.ElementTree cannot decode multi-byte encodings declared in
    # the XML prolog. This is a real limitation, not a synthetic fault; the
    # source has not served Shift_JIS since switching to UTF-8 by 2024.
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response("keio_20190909043234.xml"),
        )) as client:
            provider = KeioProvider(client=client)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert len(provider.unknown_lines) == 7

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "wrong_root", "missing_emergency", "missing_message", "empty_message",
    "missing_time", "bad_time", "not_xml",
])
def test_synthetic_structural_failures_preserve_previous_snapshot(fault: str) -> None:
    normal = (_FIXTURES / "keio_normal.xml").read_text(encoding="utf-8")
    broken_text = {
        "wrong_root": normal.replace("<unkou>", "<unkouX>").replace("</unkou>", "</unkouX>"),
        "missing_emergency": normal.replace("<emergency>false</emergency>", ""),
        "missing_message": "\n".join(
            line for line in normal.splitlines() if "unkouInformation" not in line
        ),
        "empty_message": normal.replace(
            "京王線・井の頭線は平常通り運転しています。", "",
        ),
        "missing_time": "\n".join(line for line in normal.splitlines() if "<time>" not in line),
        "bad_time": normal.replace("2026/11/03 12:40", "not-a-time"),
        "not_xml": "<html>maintenance</html>",
    }[fault]
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            return httpx.Response(200, text=broken_text)
        return _response("keio_normal.xml")

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeioProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_unrecognized_emergency_value_is_unknown_not_error() -> None:
    # No future/legacy third state has been observed; this keeps the
    # existing structure but swaps the boolean for an unmodelled value.
    normal = (_FIXTURES / "keio_normal.xml").read_text(encoding="utf-8")
    text = normal.replace("<emergency>false</emergency>", "<emergency>maintenance</emergency>")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=text),
        )) as client:
            provider = KeioProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            alert, = provider.alerts
            assert alert.affected_line_ids == ()
            assert "平常通り運転しています" in alert.description

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [
    "京王線・井の頭線は平常通り運転しています。\n一部列車に遅れが出ています。",
    "京王線は平常通り運転しています。",
])
def test_synthetic_false_flag_with_unverified_body_is_unknown(body: str) -> None:
    # Only the fixed sentence has been observed with emergency=false; another
    # body under the same flag is kept as raw text instead of being discarded.
    normal = (_FIXTURES / "keio_normal.xml").read_text(encoding="utf-8")
    text = normal.replace("京王線・井の頭線は平常通り運転しています。", body)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=text),
        )) as client:
            provider = KeioProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            alert, = provider.alerts
            assert alert.affected_line_ids == () and alert.description == body

    asyncio.run(scenario())


def test_fetch_error_and_tracker_selection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeioProvider(client=client)
            assert "keio" in {p.provider_id for p in Tracker().providers}
            tracker = Tracker(enabled_providers=("keio",), overrides=(provider,))
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {provider.provider_id}
            assert isinstance(captured.value.errors[ProviderId("keio")], FetchError)

    asyncio.run(scenario())
