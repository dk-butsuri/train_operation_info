"""Official normal/incident XML; mutations below are explicitly synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import LINE_CATALOG, AlertEffect, LineScope, LineStatus, UsagePermission
from train_operation_info.providers.tobu import TobuProvider
from train_operation_info.providers.yahoo import YahooProvider, YahooRouteId

_FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (_FIXTURES / f"tobu_{name}.xml").read_bytes()


@pytest.mark.parametrize(("name", "affected"), [
    ("normal", 0), ("20240816070042", 12), ("20240827122946", 4),
])
def test_official_xml_notices_and_scopes(name: str, affected: int) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://www.tobu.co.jp/file/trainop/trainop.xml"
            return httpx.Response(200, content=_fixture(name))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TobuProvider(client=client)
            assert len(provider.unknown_lines) == 12
            await provider.refresh()
            assert len(provider.lines) == 12
            assert len(provider.affected_lines) == affected
            assert len(provider.alerts) == affected
            assert provider.delay_lines == () and provider.unknown_lines == ()
            assert sum(line.scope is LineScope.GROUP for line in provider.lines) == 8
            assert provider.tojo.scope is LineScope.LINE
            individual = YahooProvider().get_source_line(YahooRouteId("639/0"))
            assert individual is not None and provider.isesaki_north.line_id != individual.line_id
            assert all(line.operator is LINE_CATALOG[line.line_id].operator for line in provider.lines)
            assert all(line.updated_at is None for line in provider.lines)
            assert all(line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                       for line in provider.lines)
            assert provider.metadata.usage_permission is UsagePermission.PRIVATE_USE_ONLY
            if name == "20240827122946":
                assert "踏切安全確認" in provider.skytree.alerts[0].description
                assert "一部列車に遅れ" in provider.skytree.alerts[0].description
                assert provider.sl_dl.status is LineStatus.NORMAL
                assert provider.isesaki_north.status is LineStatus.ALERT
                assert provider.nikko_north.status is LineStatus.NORMAL
                assert provider.isesaki_north.alerts[0].affected_line_ids == (provider.isesaki_north.line_id,)
                assert provider.isesaki_north.alerts[0].effect is AlertEffect.OTHER
            if name == "20240816070042":
                assert "17時以降" in provider.skytree.alerts[0].description
                assert "13時以降" in provider.urban_park.alerts[0].description
                assert "副都心線" in provider.tojo.alerts[0].description
            assert not client.is_closed

    asyncio.run(scenario())


def test_tracker_selection_recovery_and_shared_ids() -> None:
    current = _fixture("20240827122946")
    requests: list[str] = []

    async def scenario() -> None:
        nonlocal current

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(200, content=current)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TobuProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert requests == []
            tracker = Tracker(enabled_providers=("tobu",), overrides=(provider,))
            assert tracker.tobu is provider and tracker.providers == (provider,)
            await tracker.refresh()
            old = provider.skytree
            current = _fixture("normal")
            await tracker.refresh()
            assert len(requests) == 2
            assert old.status is LineStatus.ALERT
            assert provider.skytree is not old
            assert tracker.affected_lines == () and tracker.alerts == ()
            assert all(line.status is LineStatus.NORMAL for line in tracker.lines)
            yahoo = YahooProvider()
            for official, source in [(provider.skytree, "77/0"), (provider.urban_park, "81/0"),
                                     (provider.tojo, "82/0"), (provider.ogose, "83/0")]:
                other = yahoo.get_source_line(YahooRouteId(source))
                assert other is not None and other.line_id == official.line_id
                assert other is not official and other.status is LineStatus.UNKNOWN
            default = Tracker()
            assert default.tobu in default.providers

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "root", "status", "missing_info", "duplicate_info", "missing_pair", "duplicate_pair",
    "unknown_route", "reordered_route", "missing_description", "empty_description",
    "invalid_xml", "network",
])
def test_synthetic_failure_keeps_previous_snapshot(fault: str) -> None:
    root = ET.fromstring(_fixture("20240827122946"))
    info = root[0]
    if fault == "root":
        root.tag = "other"
    elif fault == "status":
        root.set("stat", "error")
    elif fault == "missing_info":
        root.remove(info)
    elif fault == "duplicate_info":
        root.append(ET.fromstring(ET.tostring(info)))
    elif fault == "missing_pair":
        info.remove(info[0])
        info.remove(info[0])
    elif fault == "duplicate_pair":
        info.append(ET.fromstring(ET.tostring(info[0])))
        info.append(ET.fromstring(ET.tostring(info[1])))
    elif fault == "unknown_route":
        info[0].text = "新線"
    elif fault == "reordered_route":
        info[0].text, info[2].text = info[2].text, info[0].text
    elif fault == "missing_description":
        info.remove(info[1])
    elif fault == "empty_description":
        info[1].clear()
    invalid = b"<rsp" if fault == "invalid_xml" else ET.tostring(root, encoding="utf-8")
    broken = False

    async def scenario() -> None:
        nonlocal broken

        def handler(request: httpx.Request) -> httpx.Response:
            if broken and fault == "network":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(200, content=invalid if broken else _fixture("20240827122946"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TobuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError if fault == "network" else ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_unfamiliar_notice_and_html_keep_original_text() -> None:
    root = ET.fromstring(_fixture("normal"))
    root[0][1].text = "未確認のお知らせ<br>現在は調査中。以前は運転を見合わせました。"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, content=ET.tostring(root, encoding="utf-8"),
        ))) as client:
            provider = TobuProvider(client=client)
            await provider.refresh()
            assert provider.nikko_express.status is LineStatus.ALERT
            assert provider.nikko_express.source_status == "未確認のお知らせ\n現在は調査中。以前は運転を見合わせました。"
            assert provider.nikko_express.alerts[0].description == provider.nikko_express.source_status
            assert provider.isesaki_express.status is LineStatus.NORMAL

    asyncio.run(scenario())
