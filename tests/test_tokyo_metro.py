"""Real normal feed; incident feeds are explicitly synthetic, history-backed cases."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.tokyo_metro import TokyoMetroProvider
from train_operation_info.providers.tokyo_metro.provider import _SourceStatus

_FIXTURES = Path(__file__).parent / "fixtures"
_FEED = "https://www.tokyometro.jp/library/common/operation/status.json"


def _normal() -> bytes:
    return (_FIXTURES / "tokyo_metro_normal.json").read_bytes()


def _synthetic(label: str, body: str = "合成テスト：以前は運転見合わせ。現在の案内です。") -> bytes:
    data = _SourceStatus.model_validate_json(_normal())
    target = data.jp.lines[3]
    target.status_info = label
    target.status_icon = "synthetic_incident_icon"
    target.status = 999  # Unverified numeric codes never determine severity.
    target.contents = body
    target.section = "中野～西船橋駅間"
    target.cause = "合成テストの原因"
    return data.model_dump_json().encode()


def test_real_normal_feed_canonical_routes_and_metadata() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.method == "GET"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=_normal())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("tokyo_metro",), client=client)
            provider = tracker.tokyo_metro
            assert len(provider.unknown_lines) == 9
            await tracker.refresh()
            assert requests == [_FEED]
            assert provider.lines == (
                provider.ginza, provider.marunouchi, provider.hibiya, provider.tozai,
                provider.chiyoda, provider.yurakucho, provider.hanzomon,
                provider.namboku, provider.fukutoshin,
            )
            assert len(provider.lines) == 9
            for line in provider.lines:
                assert line.status is LineStatus.NORMAL and line.source_status == "平常運転"
                assert line.updated_at is None
                assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
                assert line.provider_id == ProviderId("tokyo_metro")
                assert line.operator.name == "東京メトロ"
                assert len(line.source_line_names) == 1
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo is not line
                assert line.operator == yahoo.operator
                assert yahoo.status is LineStatus.UNKNOWN
            assert provider.tozai.source_url.endswith("/touzai.html")
            assert provider.namboku.source_url.endswith("/nanboku.html")
            assert not provider.alerts  # Old normal-feed causes must not create alerts.
            assert not provider.affected_lines and not provider.unknown_lines
            assert not client.is_closed
        metadata = provider.metadata
        assert metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
        assert str(metadata.terms_url) == "https://www.tokyometro.jp/terms/index.html"
        assert metadata.reviewed_at.utcoffset() == timedelta(0)
        assert provider.provider_id in {p.provider_id for p in Tracker().providers}
    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "expected"), [
    ("遅延", LineStatus.DELAYED),
    ("一部列車遅延", LineStatus.DELAYED),
    ("運転見合わせ", LineStatus.SUSPENDED),
    ("折返し運転", LineStatus.PARTIAL_SUSPENSION),
    ("ダイヤ乱れ", LineStatus.ALERT),
    ("運転再開・ダイヤ乱れ", LineStatus.ALERT),
    ("合成の未知状態", LineStatus.UNKNOWN),
    ("運転終了", LineStatus.UNKNOWN),
    ("平常運転", LineStatus.UNKNOWN),
])
def test_synthetic_incident_recovery_and_text_preservation(label: str, expected: LineStatus) -> None:
    content = _synthetic(label, "合成テスト<br>以前は運転見合わせ。<script>bad()</script>現在の案内。")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content),
        )) as client:
            provider = TokyoMetroProvider(client=client)
            await provider.refresh()
            line = provider.tozai
            assert line.status is expected
            assert line.source_status == label
            alert, = line.alerts
            assert "合成テスト\n以前は運転見合わせ。" in alert.description
            assert "bad()" not in alert.description and "<br>" not in alert.description
            assert "影響区間：中野～西船橋駅間" in alert.description
            assert "原因：合成テストの原因" in alert.description
            assert alert.affected_line_ids == (line.line_id,)
            assert all(other.status is LineStatus.NORMAL for other in provider.lines if other is not line)
            assert provider.delay_lines == ((line,) if expected is LineStatus.DELAYED else ())
            content = _normal()
            await provider.refresh()
            assert not provider.alerts and not provider.affected_lines and not provider.unknown_lines
            assert line.alerts == (alert,)  # Previous immutable snapshot stays intact.
    asyncio.run(scenario())


class _HistoryItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    date: str
    contents: str


class _History(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    items: list[_HistoryItem]


def test_real_history_evidence_for_synthetic_labels() -> None:
    history = _History.model_validate_json((_FIXTURES / "tokyo_metro_history_touzai.json").read_bytes())
    assert any(item.contents.startswith("【運転見合わせ】") for item in history.items)
    assert any(item.contents.startswith("【折返し運転】") for item in history.items)
    assert any(item.contents.startswith("【運転再開・ダイヤ乱れ】") for item in history.items)
    assert history.items[0].contents == "現在、平常どおり運転しています。"
    assert history.items[0].date == "2026/11/01 08:15"


@pytest.mark.parametrize("mutation", [
    "missing_route", "duplicate_route", "unknown_route", "wrong_name", "wrong_alpha",
    "wrong_database", "empty_body", "empty_label", "empty_icon", "missing_field",
    "wrong_type", "missing_jp", "malformed_json",
])
def test_synthetic_invalid_response_preserves_previous_incident(mutation: str) -> None:
    data = _SourceStatus.model_validate_json(_synthetic("運転見合わせ"))
    item = data.jp.lines[-1]
    if mutation == "missing_route":
        data.jp.lines.pop()
    elif mutation == "duplicate_route":
        data.jp.lines.append(item)
    elif mutation == "unknown_route":
        item.line_id = 999
    elif mutation == "wrong_name":
        item.line_name = "未登録線"
    elif mutation == "wrong_alpha":
        item.name_alpha = "unknown"
    elif mutation == "wrong_database":
        item.name_alpha_db = "unknown"
    elif mutation == "empty_body":
        item.contents = "<script>bad()</script>"
    elif mutation == "empty_label":
        item.status_info = " "
    elif mutation == "empty_icon":
        item.status_icon = ""
    broken = data.model_dump_json().encode()
    if mutation == "missing_field":
        broken = broken.replace(b'"contents":', b'"unused":', 1)
    elif mutation == "wrong_type":
        broken = broken.replace(b'"line_id":1,', b'"line_id":"1",', 1)
    elif mutation == "missing_jp":
        broken = b'{"en":{"lines":[]}}'
    elif mutation == "malformed_json":
        broken = b"broken"
    content = _synthetic("運転見合わせ")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=content),
        )) as client:
            provider = TokyoMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            content = broken
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["normal_body", "normal_icon", "normal_code", "incident_icon"])
def test_synthetic_contradictions_are_unknown(mutation: str) -> None:
    data = _SourceStatus.model_validate_json(_normal())
    item = data.jp.lines[0]
    if mutation == "normal_body":
        item.contents = "合成テスト：運行情報の提供時間外です。"
    elif mutation == "normal_icon":
        item.status_icon = "unknown"
    elif mutation == "normal_code":
        item.status = 99
    else:
        item.status_info = "遅延"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=data.model_dump_json().encode()),
        )) as client:
            provider = TokyoMetroProvider(client=client)
            await provider.refresh()
            assert provider.ginza.status is LineStatus.UNKNOWN
            assert provider.ginza.alerts
    asyncio.run(scenario())


def test_selection_injection_and_failure_isolation() -> None:
    requests: list[str] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _FEED:
            return httpx.Response(503 if fail else 200, content=_synthetic("遅延"))
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TokyoMetroProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), overrides=(provider,), client=client)
            await disabled.refresh()
            assert _FEED not in requests
            tracker = Tracker(enabled_providers=("tokyo_metro", "hankyu"), overrides=(provider,), client=client)
            assert tracker.tokyo_metro is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("tokyo_metro")}
            assert isinstance(captured.value.errors[ProviderId("tokyo_metro")], FetchError)
            assert provider.lines is previous
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL
    asyncio.run(scenario())
