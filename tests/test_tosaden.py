"""Official normal/typhoon fixtures; malformed and unknown cases are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, LineId, LineStatus, ProviderId, UsagePermission,
)
from train_operation_info.providers.tosaden import TosadenProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.tosaden.co.jp/info/service.php?ID=1"
_LINE_ID = LineId("jp:operator_74ae511377a2:line_d1d5a8a2e706")


def _html(name: str = "normal") -> str:
    return (_FIXTURES / f"tosaden_{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(("name", "expected"), [
    ("normal", LineStatus.NORMAL),
    ("20230602090407", LineStatus.NORMAL),
    ("20220918071853", LineStatus.ALERT),
])
def test_official_snapshots_and_clearing_with_separate_normal_capture(
    name: str, expected: LineStatus,
) -> None:
    html = _html(name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL
        return httpx.Response(200, text=html)

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("tosaden",), client=client)
            provider = tracker.tosaden
            assert provider.lines[0].status is LineStatus.UNKNOWN
            await tracker.refresh()
            line = provider.main
            assert line.status is expected and line.line_id == _LINE_ID
            assert line.name == "とさでん交通線" and line.operator.name == "とさでん交通"
            assert line.provider_id == ProviderId("tosaden") and line.source_url == _URL
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            assert line.updated_at is None
            yahoo_line = tracker.yahoo.get_line(_LINE_ID)
            assert yahoo_line is not None and yahoo_line is not line
            assert yahoo_line.operator == line.operator and yahoo_line.status is LineStatus.UNKNOWN
            assert provider.delay_lines == ()
            if expected is LineStatus.ALERT:
                alert, = provider.alerts
                assert "台風14号" in alert.title
                assert "始発便より全線、終日運休いたします。" in alert.description
                assert "9月20日(火)" in alert.description
                assert alert.affected_line_ids == (_LINE_ID,)
                assert alert.effect is AlertEffect.OTHER
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.active_from is None and alert.active_until is None
                assert provider.unclassified_alerts == (alert,)
                assert provider.affected_lines == (line,)
            else:
                assert not provider.alerts and not provider.affected_lines
            html = _html()
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.affected_lines
            assert not client.is_closed
            assert line.status is expected  # Prior snapshots are immutable.

    asyncio.run(scenario())


@pytest.mark.parametrize("encoding", ["utf-8", "euc-jp"])
def test_html_declared_encoding_without_http_charset(encoding: str) -> None:
    # Synthetic re-encoding of unchanged extracted markup, not another capture.
    html = _html("20220918071853").replace('charset="utf-8"', f'charset="{encoding}"')

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html.encode(encoding, errors="xmlcharrefreplace")),
        )) as client:
            provider = TosadenProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.ALERT
            assert "始発便より全線" in provider.alerts[0].description

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_category", "duplicate_category", "wrong_category", "missing_panel", "duplicate_panel",
    "missing_title", "duplicate_title", "empty_title", "missing_body", "duplicate_body", "empty_body",
    "duplicate_policy", "unknown_policy", "policy_only",
])
def test_synthetic_malformed_response_keeps_previous_notice(mutation: str) -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    action, field = mutation.split("_", 1)
    selector = {
        "category": "h2.tit_train", "panel": "#main_a", "title": "#main_header h1",
        "body": "#main_body", "policy": "#main_body h2", "only": "#main_body",
    }[field]
    target = soup.select_one(selector)
    assert target is not None
    if action == "missing":
        target.decompose()
    elif action == "duplicate":
        target.insert_after(BeautifulSoup(str(target), "html.parser"))
    elif action == "empty":
        target.clear()
    elif action == "policy":
        target.clear()
        target.append(BeautifulSoup('<h2>運行情報について</h2><p>掲載基準</p>', "html.parser"))
    else:
        target.string = "路線バス" if field == "category" else "合成の不明な見出し"
    html = _html("20220918071853")

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = TosadenProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = str(soup)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize(("notice", "expected"), [
    ("合成：現在、遅れが発生しています。", LineStatus.ALERT),
    ("合成：一部区間で運転を見合わせています。", LineStatus.ALERT),
    ("合成：当分の間運休します。", LineStatus.ALERT),
    ("現在、30分以上の遅れは発生していません。合成：別区間の運休案内。", LineStatus.UNKNOWN),
])
def test_synthetic_unstructured_notices_are_retained_without_inferred_effect(
    notice: str, expected: LineStatus,
) -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    body = soup.select_one("#main_body")
    assert body is not None
    body.clear()
    body.string = notice

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = TosadenProvider(client=client)
            await provider.refresh()
            assert provider.main.status is expected
            assert provider.alerts[0].description == notice
            assert provider.alerts[0].timing is AlertTiming.UNKNOWN
            assert provider.main.updated_at is None

    asyncio.run(scenario())


def test_selection_injection_and_failure_isolation() -> None:
    failing = False
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            return httpx.Response(503 if failing else 200, text=_html("20220918071853"))
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal failing
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TosadenProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), overrides=(provider,), client=client)
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("tosaden", "hankyu"), overrides=(provider,), client=client)
            assert tracker.tosaden is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            failing = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("tosaden")}
            assert isinstance(captured.value.errors[ProviderId("tosaden")], FetchError)
            assert provider.lines is previous
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL

    asyncio.run(scenario())


def test_default_registration_and_metadata() -> None:
    tracker = Tracker()
    provider = tracker.tosaden
    assert provider in tracker.providers
    assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(provider.metadata.terms_url) == "https://www.tosaden.co.jp/info/sitepolicy.php"
    assert provider.metadata.additional_terms_urls
    assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
