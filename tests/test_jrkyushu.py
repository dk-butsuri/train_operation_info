"""Real normal XML; incidents and mutations are synthetic. Long-term flags are not fetched."""

import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineScope, LineStatus, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.jrkyushu import JrKyushuProvider

_FIXTURES = Path(__file__).parent / "fixtures"


def _xml() -> ET.Element:
    return ET.fromstring((_FIXTURES / "jrkyushu_IDS2Web.xml").read_bytes())


def _area(root: ET.Element, name: str = "Fukuoka-Kitakyushu") -> ET.Element:
    return next(e for e in root.findall("info/aif") if e.findtext("nm") == name)


def _incident(root: ET.Element, name: str = "Fukuoka-Kitakyushu", body: str = "明日は運休します。現在は平常運転です。", time: str = "20261102123456") -> None:
    area = _area(root, name)
    state = area.find("sts")
    assert state is not None
    state.text = "1"
    entry = ET.SubElement(area, "eif")
    ET.SubElement(entry, "time").text = time
    ET.SubElement(entry, "txt").text = body


def _response(request: httpx.Request, *, payload: bytes | None = None) -> httpx.Response:
    assert request.url.host == "www.jrkyushu.co.jp"
    assert request.method == "GET"
    assert request.headers["User-Agent"] == USER_AGENT
    filename = request.url.path.rsplit("/", 1)[-1]
    assert filename == "IDS2Web.xml"
    content = payload if payload is not None else (_FIXTURES / "jrkyushu_IDS2Web.xml").read_bytes()
    return httpx.Response(200, content=content)


def test_real_capture_excludes_structurally_separate_long_term_flags() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _response(request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("jrkyushu",), client=client)
            yahoo_before = tracker.yahoo.lines
            provider = tracker.jrkyushu
            assert len(provider.unknown_lines) == 8
            await tracker.refresh()
            # kuma/kago flags were 1 at capture time; the separate flag files are not requested.
            assert calls == ["/trains/info/data/IDS2Web.xml"]
            assert len(provider.lines) == 8
            assert all(line.status is LineStatus.NORMAL for line in provider.lines)
            assert not provider.alerts and not provider.affected_lines and not provider.delay_lines
            for line in provider.lines[:6]:
                assert line.scope is LineScope.GROUP
                assert line.operator.name == "JR九州"
                assert line.source_url.endswith(".html")
            for line in provider.lines[6:]:
                assert line.scope is LineScope.LINE and line.status is LineStatus.NORMAL
            assert provider.fukuoka_kitakyushu.source_line_names == ("福岡・北九州エリア",)
            assert provider.kyushu_shinkansen.line_id == LineId("jp:jr_kyushu:kyushu_shinkansen")
            assert provider.nishi_kyushu_shinkansen.line_id == LineId("jp:jr_kyushu:nishi_kyushu_shinkansen")
            assert all(line.updated_at is None for line in provider.lines)
            assert all(line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0) for line in provider.lines)
            assert provider.metadata.usage_permission is UsagePermission.UNSPECIFIED
            assert tracker.yahoo.lines is yahoo_before
            hisatsu = tracker.yahoo.get_line(LineId("jp:jr_kyushu:line_40d04aff0de2"))
            assert hisatsu is not None and hisatsu.status is LineStatus.UNKNOWN
            assert hisatsu.operator is provider.kumamoto.operator

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [
    "運転を見合わせています。", "運転再開しました。", "明日は運休します。現在は平常運転です。",
    "長期運休は実施しません。", "引用：『日豊本線は運休』という情報を取り消します。",
])
def test_synthetic_notices_do_not_classify_prose(body: str) -> None:
    root = _xml()
    _incident(root, body=body)
    _incident(root, time="202611021245", body="追加の案内\n原文を保持")
    _incident(root, "Kyushu-Shinkansen", body=body)
    payload = ET.tostring(root, encoding="utf-8")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: _response(r, payload=payload),
        )) as client:
            provider = JrKyushuProvider(client=client)
            await provider.refresh()
            line = provider.fukuoka_kitakyushu
            assert line.status is LineStatus.ALERT
            assert len(line.alerts) == 2
            assert line.alerts[0].description == body
            assert line.alerts[1].description == "追加の案内\n原文を保持"
            for alert in line.alerts:
                assert alert.affected_line_ids == ()
                assert alert.effect is AlertEffect.OTHER and alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None
            assert line.updated_at == datetime.fromisoformat("2026-11-02T12:45:00+09:00")
            shin = provider.kyushu_shinkansen
            assert shin.status is LineStatus.ALERT
            assert shin.updated_at == datetime.fromisoformat("2026-11-02T12:34:00+09:00")
            assert shin.alerts[0].affected_line_ids == (shin.line_id,)
            assert provider.oita.status is LineStatus.NORMAL
            assert not provider.delay_lines and not provider.active_alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("code", ["9", "2"])
def test_synthetic_unknown_codes_are_retained(code: str) -> None:
    root = _xml()
    _incident(root, body="原文には運休と書かれています。")
    state = _area(root).find("sts")
    assert state is not None
    state.text = code

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: _response(r, payload=ET.tostring(root)),
        )) as client:
            provider = JrKyushuProvider(client=client)
            await provider.refresh()
            line = provider.fukuoka_kitakyushu
            assert line.status is LineStatus.UNKNOWN
            assert line.alerts[-1].description == f"sts={code}"
            assert line.alerts[0].description == "原文には運休と書かれています。"
            assert provider.oita.status is LineStatus.NORMAL

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", [
    "xml", "root", "missing_area", "duplicate_area", "unknown_area", "missing_info",
    "duplicate_info", "missing_status", "duplicate_status", "nested_status",
    "missing_body", "missing_time", "invalid_time", "invalid_date", "empty_body",
    "notice_without_status", "status_without_notice", "xml_http",
])
def test_synthetic_failure_preserves_entire_snapshot(kind: str) -> None:
    root = _xml()
    _incident(root)
    area = _area(root)
    entry = area.find("eif")
    assert entry is not None
    info = root.find("info")
    assert info is not None
    if kind == "root":
        root.tag = "html"
    elif kind == "missing_area":
        info.remove(area)
    elif kind == "duplicate_area":
        info.append(area)
    elif kind == "unknown_area":
        node = area.find("nm")
        assert node is not None
        node.text = "New-Area"
    elif kind == "missing_info":
        root.remove(info)
    elif kind == "duplicate_info":
        root.append(info)
    elif kind in ("missing_status", "duplicate_status", "nested_status", "notice_without_status"):
        node = area.find("sts")
        assert node is not None
        if kind == "missing_status":
            area.remove(node)
        elif kind == "duplicate_status":
            area.append(node)
        elif kind == "nested_status":
            ET.SubElement(node, "nested").text = "1"
        else:
            node.text = "0"
    elif kind == "status_without_notice":
        area.remove(entry)
    elif kind in ("missing_body", "empty_body", "missing_time", "invalid_time", "invalid_date"):
        node = entry.find("txt" if kind in ("missing_body", "empty_body") else "time")
        assert node is not None
        if kind.startswith("missing"):
            entry.remove(node)
        else:
            node.text = " " if kind == "empty_body" else "bad" if kind == "invalid_time" else "20260230120000"
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not broken:
            return _response(request)
        if kind == "xml_http":
            return httpx.Response(503)
        return _response(request, payload=b"<broken" if kind == "xml" else ET.tostring(root))

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrKyushuProvider(client=client)
            await provider.refresh()
            before = provider.lines
            broken = True
            with pytest.raises(FetchError if kind.endswith("http") else ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_synthetic_recovery_clears_notices_and_dates() -> None:
    root = _xml()
    _incident(root)
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, payload=ET.tostring(_xml() if recovered else root))

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrKyushuProvider(client=client)
            await provider.refresh()
            assert provider.alerts and provider.fukuoka_kitakyushu.updated_at is not None
            recovered = True
            await provider.refresh()
            assert not provider.alerts and not provider.affected_lines
            assert all(line.status is LineStatus.NORMAL and line.updated_at is None for line in provider.lines)

    asyncio.run(scenario())


def test_tracker_injection_selection_and_other_provider_failure() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return _response(request) if request.url.host == "www.jrkyushu.co.jp" else httpx.Response(503)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrKyushuProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert calls == [] and disabled.jrkyushu is provider
            assert "jrkyushu" in {p.provider_id for p in Tracker().providers}
            tracker = Tracker(enabled_providers=("jrkyushu", "jrw"), overrides=(provider,), client=client)
            with pytest.raises(RefreshError) as caught:
                await tracker.refresh()
            assert set(caught.value.errors) == {"jrw"}
            assert not provider.unknown_lines and tracker.jrkyushu is provider

    asyncio.run(scenario())


def test_saved_evidence_hashes() -> None:
    manifest = json.loads((_FIXTURES / "jrkyushu_manifest.json").read_text(encoding="utf-8"))
    for record in manifest:
        assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record["fixture_sha256"]
        assert record["fixture_sha256"] == record["original_sha256"]
