"""Live normal capture plus synthetic mutations of the official XML/legend."""

import asyncio
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, AlertTiming, LineId, LineStatus, OperatorId, UsagePermission,
)
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.mtr import MtrProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.mtr.com.hk/alert/ryg_line_status_lite.xml"
_ROUTES = (
    ("TWL", "Tsuen Wan Line", "tsuen_wan"),
    ("KTL", "Kwun Tong Line", "kwun_tong"),
    ("ISL", "Island Line", "island"),
    ("SIL", "South Island Line", "south_island"),
    ("TKL", "Tseung Kwan O Line", "tseung_kwan_o"),
    ("TCL", "Tung Chung Line", "tung_chung"),
    ("DRL", "Disneyland Resort Line", "disneyland_resort"),
    ("AEL", "Airport Express", "airport_express"),
    ("EAL", "East Rail Line", "east_rail"),
    ("TML", "Tuen Ma Line", "tuen_ma"),
)


def _synthetic() -> ET.Element:
    root = ET.Element("ryg_status")
    ET.SubElement(root, "lastBuildDate").text = "2026-11-04 08:00:00"
    for code, name, _ in _ROUTES:
        item = ET.SubElement(root, "line")
        for key, value in (
            ("line_code", code), ("line_name", name), ("line_name_tc", "合成路綫名"),
            ("status", "green"),
        ):
            ET.SubElement(item, key).text = value
        ET.SubElement(item, "messages")
    return root


def _element(root: ET.Element, path: str) -> ET.Element:
    item = root.find(path)
    assert item is not None
    return item


def _message(root: ET.Element, title: str, link: str = "/alert/synthetic.html") -> None:
    message = ET.SubElement(_element(root, "line/messages"), "message")
    ET.SubElement(message, "title_en").text = title
    ET.SubElement(message, "url_en").text = link


def test_official_normal_capture() -> None:
    body = (_FIXTURES / "mtr_normal.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL and request.method == "GET"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=body)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("mtr",), client=client)
            assert len(tracker.unknown_lines) == 10
            await tracker.refresh()
            provider = tracker.mtr
            assert len(provider.lines) == 10
            for line, (_, name, suffix) in zip(provider.lines, _ROUTES, strict=True):
                assert line is getattr(provider, suffix)
                assert line.line_id == LineId(f"hk:mtr:{suffix}")
                assert line.name == name
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.operator.operator_id == OperatorId("hk:mtr")
                assert line.status is LineStatus.NORMAL and line.source_status == "green"
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
            assert not tracker.alerts and not tracker.unknown_lines
            assert all(line.status is LineStatus.UNKNOWN for line in tracker.singapore_mrt.lines)
            assert provider.metadata.usage_permission is UsagePermission.PRIVATE_USE_ONLY
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("code", "expected", "effect"), [
    ("yellow", LineStatus.DELAYED, AlertEffect.DELAYS),
    ("red", LineStatus.ALERT, AlertEffect.OTHER),
    ("pink", LineStatus.ALERT, AlertEffect.OTHER),
    ("typhoon", LineStatus.ALERT, AlertEffect.OTHER),
    ("grey", LineStatus.NORMAL, None),
    ("new_code", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
])
def test_synthetic_states_and_recovery(
    code: str, expected: LineStatus, effect: AlertEffect | None,
) -> None:
    root = _synthetic()
    _element(root, "line/status").text = code
    body = ET.tostring(root)

    async def scenario() -> None:
        nonlocal body
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body),
        )) as client:
            provider = MtrProvider(client=client)
            await provider.refresh()
            assert provider.tsuen_wan.status is expected
            assert provider.tsuen_wan.source_status == code
            assert all(line.status is LineStatus.NORMAL for line in provider.lines[1:])
            if effect is not None:
                alert, = provider.alerts
                assert alert.effect is effect
                assert alert.affected_line_ids == (LineId("hk:mtr:tsuen_wan"),)
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is alert.active_until is None
            else:
                assert not provider.alerts
            body = ET.tostring(_synthetic())
            await provider.refresh()
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert not provider.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("code", ["green", "grey", "yellow", "red", "new_code"])
def test_synthetic_messages_preserve_scope_and_do_not_classify_prose(code: str) -> None:
    root = _synthetic()
    _element(root, "line/status").text = code
    _message(root, "Synthetic: Island Line suspended tomorrow, not today.<br/>No current suspension.")
    _message(root, "Synthetic: service resumed", "")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=ET.tostring(root)),
        )) as client:
            provider = MtrProvider(client=client)
            await provider.refresh()
            expected = {"yellow": LineStatus.DELAYED, "new_code": LineStatus.UNKNOWN}.get(code, LineStatus.ALERT)
            assert provider.tsuen_wan.status is expected
            assert provider.island.status is LineStatus.NORMAL
            assert len(provider.alerts) == 2
            assert "tomorrow" in provider.alerts[0].description
            assert "<br" not in provider.alerts[0].title
            assert "https://www.mtr.com.hk/alert/synthetic.html" in provider.alerts[0].description
            for alert in provider.alerts:
                assert alert.language == "en"
                assert alert.affected_line_ids == (LineId("hk:mtr:tsuen_wan"),)
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is alert.active_until is None

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [
    "root", "missing_line", "duplicate_line", "unknown_line", "wrong_name", "missing_status",
    "duplicate_status", "empty_status", "nested_status", "messages", "message_child", "message_text",
    "missing_title", "empty_title", "invalid_link", "missing_build_date", "maintenance", "http", "network",
])
def test_synthetic_failures_preserve_previous_snapshot(failure: str) -> None:
    root = _synthetic()
    line = _element(root, "line")
    if failure == "root":
        root.tag = "maintenance"
    elif failure == "missing_line":
        root.remove(line)
    elif failure == "duplicate_line":
        root.append(ET.fromstring(ET.tostring(line)))
    elif failure == "unknown_line":
        _element(line, "line_code").text = "LR"
    elif failure == "wrong_name":
        _element(line, "line_name").text = "Island Line"
    elif failure == "missing_status":
        line.remove(_element(line, "status"))
    elif failure == "duplicate_status":
        ET.SubElement(line, "status").text = "green"
    elif failure == "empty_status":
        _element(line, "status").text = ""
    elif failure == "nested_status":
        ET.SubElement(_element(line, "status"), "status").text = "green"
    elif failure == "messages":
        line.remove(_element(line, "messages"))
    elif failure == "message_child":
        ET.SubElement(_element(line, "messages"), "changed")
    elif failure == "message_text":
        _element(line, "messages").text = "Synthetic: changed message format"
    elif failure in {"missing_title", "empty_title", "invalid_link"}:
        _message(root, "Synthetic alert", "javascript:alert(1)" if failure == "invalid_link" else "")
        message = _element(line, "messages/message")
        if failure == "missing_title":
            message.remove(_element(message, "title_en"))
        elif failure == "empty_title":
            _element(message, "title_en").text = "<br/>"
    elif failure == "missing_build_date":
        root.remove(_element(root, "lastBuildDate"))
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not broken:
            return httpx.Response(200, content=ET.tostring(_synthetic()))
        if failure == "network":
            raise httpx.ConnectError("Synthetic network failure", request=request)
        if failure == "http":
            return httpx.Response(503)
        return httpx.Response(200, content=b"<html>maintenance" if failure == "maintenance" else ET.tostring(root))

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = MtrProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            broken = True
            with pytest.raises(FetchError if failure in {"http", "network"} else ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())
