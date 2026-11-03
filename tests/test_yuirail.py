"""Real normal notices, archived abnormal notices and synthetic malformed payloads."""

import asyncio
from datetime import timedelta
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, DataFormat, LineId, LineStatus, ProviderId, UsagePermission,
)
from train_operation_info.providers.yuirail import YuiRailProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_FEED = "https://www.yui-rail.co.jp/common/json/data/operation_info.json"
_LINE_ID = LineId("jp:operator_95b01abb482d:line_b8a42de95ac6")
_NORMAL = _FIXTURES / "yuirail_normal.json"
# Archived: normal message without the trailing period (2026-03-26 UTC).
_ARCHIVE_NORMAL = _FIXTURES / "yuirail_20260326033336.json"
# Archived: all-day suspension for Typhoon No. 6, 2026-06-01.
_ARCHIVE_SUSPENSION = _FIXTURES / "yuirail_20260601101306.json"
# Archived: normal operation plus a next-day typhoon caution, 2026-08-25.
_ARCHIVE_NOTICE = _FIXTURES / "yuirail_20260825141333.json"


def _payload(name: Path) -> dict[str, object]:
    data: object = json.loads(name.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _serve(body: bytes) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


async def _refresh(body: bytes) -> YuiRailProvider:
    async with httpx.AsyncClient(transport=_serve(body)) as client:
        provider = YuiRailProvider(client=client)
        await provider.refresh()
        assert not client.is_closed
        return provider


def _jp_text(payload: dict[str, object]) -> str:
    jp = payload["jp"]
    assert isinstance(jp, dict)
    text = jp["text"]
    assert isinstance(text, str)
    return text


def test_official_normal_notice_and_shared_identity() -> None:
    provider = asyncio.run(_refresh(_NORMAL.read_bytes()))
    line = provider.main
    assert line.line_id == _LINE_ID
    assert line.name == "ゆいレール" and line.operator.name == "沖縄都市モノレール"
    assert line.provider_id == ProviderId("yuirail")
    assert line.source_url == "https://www.yui-rail.co.jp/"
    assert line.status is LineStatus.NORMAL
    assert line.source_status == "現在、平常通り運行しております。"
    assert line.alerts == ()
    assert line.updated_at is None
    assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)


def test_archived_normal_message_without_period_is_normal() -> None:
    provider = asyncio.run(_refresh(_ARCHIVE_NORMAL.read_bytes()))
    assert provider.main.status is LineStatus.NORMAL
    assert provider.main.source_status == "現在、平常通り運行しております"


def test_archived_suspension_stays_alert_without_inferred_effect() -> None:
    payload = _payload(_ARCHIVE_SUSPENSION)
    text = _jp_text(payload)
    provider = asyncio.run(_refresh(_ARCHIVE_SUSPENSION.read_bytes()))
    line = provider.main
    assert line.status is LineStatus.ALERT
    assert line.source_status == text
    alert, = line.alerts
    assert alert.title == "運行情報" and alert.description == text
    assert alert.effect is AlertEffect.OTHER
    assert alert.timing is AlertTiming.UNKNOWN
    assert alert.affected_line_ids == (_LINE_ID,)
    assert alert.language == "ja"
    assert provider.delay_lines == () and provider.affected_lines == (line,)


def test_archived_normal_with_caution_is_alert_not_normal() -> None:
    provider = asyncio.run(_refresh(_ARCHIVE_NOTICE.read_bytes()))
    line = provider.main
    assert line.status is LineStatus.ALERT
    assert "現在、平常どおり運行しています" in (line.source_status or "")
    assert line.alerts and line.alerts[0].effect is AlertEffect.OTHER


@pytest.mark.parametrize("mutation", [
    "not_json", "top_level_array", "missing_jp", "jp_not_object", "missing_text",
    "text_not_string", "missing_link", "empty_text",
])
def test_synthetic_malformed_payload_preserves_previous_notice(mutation: str) -> None:
    payload = _payload(_NORMAL)
    if mutation == "not_json":
        body = b"<html>maintenance</html>"
    elif mutation == "top_level_array":
        body = b"[]"
    else:
        jp = payload["jp"]
        assert isinstance(jp, dict)
        if mutation == "missing_jp":
            del payload["jp"]
        elif mutation == "jp_not_object":
            payload["jp"] = "現在、平常通り運行しております。"
        elif mutation == "missing_text":
            del jp["text"]
        elif mutation == "text_not_string":
            jp["text"] = 1
        elif mutation == "missing_link":
            del jp["link"]
        else:
            jp["text"] = "   "
        body = json.dumps(payload, ensure_ascii=False).encode()

    async def scenario() -> None:
        current = _NORMAL.read_bytes()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=current)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YuiRailProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            current = body
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_transport_failure_isolated_and_selection_respected() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _FEED:
            return httpx.Response(503)
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, text=(_FIXTURES / "hankyu_normal.html").read_text(encoding="utf-8"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = YuiRailProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _FEED not in requests
            tracker = Tracker(enabled_providers=("yuirail", "hankyu"), client=client, overrides=(provider,))
            assert tracker.yuirail is provider and tracker.providers[0] is provider
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("yuirail")}
            assert isinstance(captured.value.errors[ProviderId("yuirail")], FetchError)
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
            assert provider.main.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


def test_shared_canonical_route_and_reviewed_metadata() -> None:
    tracker = Tracker()
    provider = tracker.yuirail
    assert provider in tracker.providers
    official = provider.main
    yahoo = tracker.yahoo.get_line(official.line_id)
    assert yahoo is not None and official is not yahoo
    assert official.operator == yahoo.operator
    metadata = provider.metadata
    assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert metadata.reviewed_at.utcoffset() == timedelta(0)
    assert str(metadata.terms_url) == "https://www.yui-rail.co.jp/policy/"
    assert str(metadata.source_page_url) == "https://www.yui-rail.co.jp/"
    endpoint, = metadata.endpoints
    assert endpoint.url == _FEED and endpoint.format is DataFormat.JSON
