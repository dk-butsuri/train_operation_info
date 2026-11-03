"""Official normal/advisory/disruption fixtures; malformed cases are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LineId, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.minatomirai import MinatomiraiProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.mm21railway.co.jp/service/"


def _html(name: str = "normal") -> str:
    return (_FIXTURES / f"minatomirai_{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(("fixture", "expected", "text"), [
    ("normal", LineStatus.NORMAL, ""),
    ("20221216085310", LineStatus.NORMAL, ""),
    ("20160920120337", LineStatus.ALERT, "【お知らせ】台風１６号"),
    ("20180122144419", LineStatus.DELAYED, "遅延時間：大幅な遅れ"),
    ("20191011232736", LineStatus.ALERT, "一部の列車に運休"),
    ("20191012171120", LineStatus.ALERT, "原因：台風のため"),
])
def test_official_fixtures_and_transition_to_normal(
    fixture: str, expected: LineStatus, text: str,
) -> None:
    html = _html(fixture)

    async def scenario() -> None:
        nonlocal html
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _URL
            return httpx.Response(200, text=html)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("minatomirai",), client=client)
            provider = tracker.minatomirai
            assert provider.lines[0].status is LineStatus.UNKNOWN
            await tracker.refresh()
            line = provider.main
            assert line.status is expected
            assert line.line_id == LineId("jp:operator_d2d012d773b3:line_3b169884afee")
            assert line.name == "みなとみらい線" and line.operator.name == "横浜高速鉄道"
            assert line.provider_id == ProviderId("minatomirai") and line.source_url == _URL
            assert line.updated_at is None  # Occurrence time is not update time.
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            yahoo_line = tracker.yahoo.get_line(line.line_id)
            assert yahoo_line is not None and yahoo_line is not line
            assert yahoo_line.operator == line.operator
            assert yahoo_line.status is LineStatus.UNKNOWN
            if text:
                alert, = provider.alerts
                assert text in alert.description
                assert alert.affected_line_ids == (line.line_id,)
                assert provider.affected_lines == (line,)
            else:
                assert not provider.alerts and not provider.affected_lines
            assert provider.delay_lines == ((line,) if expected is LineStatus.DELAYED else ())
            html = _html()
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL
            assert not provider.alerts and not provider.affected_lines and not provider.delay_lines
            assert line.status is expected
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "missing_info", "duplicate_info", "empty_info",
    "duplicate_table", "empty_table", "missing_value", "empty_value", "duplicate_key",
])
def test_synthetic_malformed_html_preserves_previous_snapshot(mutation: str) -> None:
    html = _html("20180122144419")
    soup = BeautifulSoup(html, "html.parser")
    action, field = mutation.split("_", 1)
    selector = {
        "panel": ".service_information", "info": ".info", "table": "table.basic",
        "value": "td", "key": "tr",
    }[field]
    target = soup.select_one(selector)
    assert target is not None
    if action == "missing":
        target.decompose()
    elif action == "empty":
        target.clear()
    else:
        target.insert_after(BeautifulSoup(str(target), "html.parser"))
    malformed = str(soup)

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = MinatomiraiProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = malformed
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["unknown_class", "normal_with_caution", "normal_with_details"])
def test_synthetic_unknown_and_contradictory_normal_retains_alert(mutation: str) -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    notice = soup.select_one(".info")
    assert notice is not None
    if mutation == "unknown_class":
        notice["class"] = "info synthetic_unknown"
    elif mutation == "normal_with_caution":
        notice["class"] = "info caution"
    else:
        notice.insert_after(BeautifulSoup(
            '<table class="basic"><tr><th>原因</th><td>合成の原因</td></tr></table>', "html.parser",
        ))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = MinatomiraiProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            assert provider.main.alerts and provider.main.updated_at is None

    asyncio.run(scenario())


def test_selection_injection_and_failure_isolation_preserve_previous_snapshot() -> None:
    failing = False
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _URL:
            return httpx.Response(503) if failing else httpx.Response(200, text=_html("20180122144419"))
        assert request.url.host == "www.hankyu.co.jp"
        return httpx.Response(200, content=(_FIXTURES / "hankyu_normal.html").read_bytes())

    async def scenario() -> None:
        nonlocal failing
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = MinatomiraiProvider(client=client)
            disabled = Tracker(enabled_providers=("hankyu",), client=client, overrides=(provider,))
            await disabled.refresh()
            assert _URL not in requests
            tracker = Tracker(enabled_providers=("minatomirai", "hankyu"), client=client, overrides=(provider,))
            assert tracker.minatomirai is provider and tracker.providers[0] is provider
            await tracker.refresh()
            previous = provider.lines
            failing = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {ProviderId("minatomirai")}
            assert isinstance(captured.value.errors[ProviderId("minatomirai")], FetchError)
            assert provider.lines is previous
            assert tracker.hankyu.kobe.status is LineStatus.NORMAL

    asyncio.run(scenario())


def test_default_registration_and_metadata() -> None:
    tracker = Tracker()
    provider = tracker.minatomirai
    assert provider in tracker.providers
    assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
    assert str(provider.metadata.terms_url) == "https://www.mm21railway.co.jp/info/sitepolicy.html"
    assert provider.metadata.reviewed_at.utcoffset() == timedelta(0)
