"""Real normal/cross-mode fixtures; railway warning/malformed cases are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from bs4.element import AttributeValueList
import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, LineStatus, UsagePermission,
)
from train_operation_info.providers.hakone_tozan import HakoneTozanProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.hakonenavi.jp/transportation/"


def _html(name: str = "normal") -> str:
    return (_FIXTURES / f"hakone_tozan_{name}.html").read_text(encoding="utf-8")


def _one(soup: BeautifulSoup | Tag, selector: str) -> Tag:
    found = soup.select_one(selector)
    assert found is not None
    return found


def _synthetic_warning() -> BeautifulSoup:
    # Common warning styling/section markup is verified on other modes in the
    # real fixtures. This T0001 warning is synthetic, not an archived incident.
    soup = BeautifulSoup(_html("20260208142500"), "html.parser")
    item = _one(soup, '[data-code="T0001"]')
    item["class"] = AttributeValueList(["operation_item", "operation_item-error"])
    state = _one(item, ".operation_state")
    state["class"] = AttributeValueList(["operation_state", "operation_state-error"])
    state.string = "運休、運転見合わせあり"
    details = BeautifulSoup(
        '<div class="operation_item_toggle"><section class="operation_sect" data-route-cd="RT0005">'
        '<p class="operation_headline">箱根湯本～強羅</p>'
        '<p class="operation_status">運休</p><p class="operation_note">'
        '運転再開の時期は未定です。別区間では運転しています。</p></section></div>',
        "html.parser",
    )
    item.append(details)
    return soup


@pytest.mark.parametrize("name", ["normal", "20230326061457", "20250321040309", "20260208142500"])
def test_real_normal_fixtures_ignore_other_modes_and_reuse_canonical_id(name: str) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET" and str(request.url) == _URL
            return httpx.Response(200, content=_html(name).encode("utf-8"))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("hakone_tozan",), client=client)
            provider = tracker.hakone_tozan
            assert provider.main.status is LineStatus.UNKNOWN
            await tracker.refresh()
            line = provider.main
            assert line.line_id == "jp:operator_5dbad158fdda:line_a0694844624f"
            assert line.name == "箱根登山鉄道線" and line.operator.name == "小田急箱根"
            assert line.provider_id == "hakone_tozan" and line.source_url == _URL
            assert line.source_status == "平常通り運行中"
            assert line.source_line_names == ("箱根登山電車",)
            assert line.status is LineStatus.NORMAL and not line.alerts
            assert line.updated_at is None  # data-debug is not a source update.
            assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
            other = tracker.yahoo.get_line(line.line_id)
            assert other is not None and other is not line
            assert other.operator == line.operator and other.status is LineStatus.UNKNOWN
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert not provider.affected_lines and not client.is_closed

    asyncio.run(scenario())


def test_synthetic_warning_preserves_details_without_inventing_full_suspension_or_timing() -> None:
    html = str(_synthetic_warning())

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = HakoneTozanProvider(client=client)
            await provider.refresh()
            old = provider.main
            assert old.status is LineStatus.ALERT
            alert, = provider.alerts
            assert alert.title == "運休、運転見合わせあり"
            assert "箱根湯本～強羅" in alert.description and "別区間では運転しています。" in alert.description
            assert "定期点検整備工事" not in alert.description  # Other mode, same HTTP body.
            assert alert.affected_line_ids == (old.line_id,)
            assert alert.effect is AlertEffect.OTHER and alert.timing is AlertTiming.UNKNOWN
            assert alert.active_from is None and alert.active_until is None
            assert old.updated_at is None and not provider.delay_lines
            assert provider.affected_lines == (old,) and not provider.active_alerts
            assert provider.unclassified_alerts == (alert,)
            # Synthetic transition to a real normal page tests clearing only;
            # this is not evidence of same-event recovery.
            html = _html()
            await provider.refresh()
            assert provider.main.status is LineStatus.NORMAL and not provider.alerts
            assert old.status is LineStatus.ALERT

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "new_label", "closed", "planned", "normal_plus_notice", "new_style", "one_warning_style", "contradictory",
])
def test_synthetic_unknown_states_remain_unknown_with_original_text(mutation: str) -> None:
    soup = _synthetic_warning() if mutation == "contradictory" else BeautifulSoup(_html(), "html.parser")
    item = _one(soup, '[data-code="T0001"]')
    state = _one(item, ".operation_state")
    if mutation == "new_label":
        state.string = "新しい表示：明日は運休予定、現在は遅れなし"
    elif mutation == "closed":
        state.string = "運行は終了しています"
    elif mutation == "planned":
        state.string = "平常通り運行予定です"
    elif mutation == "normal_plus_notice":
        item.append(BeautifulSoup('<p class="operation_caption">明日の運行についてのご案内</p>', "html.parser"))
    elif mutation == "new_style":
        state["class"] = AttributeValueList(["operation_state", "operation_state-future"])
    elif mutation == "one_warning_style":
        item["class"] = AttributeValueList(["operation_item", "operation_item-error"])
    else:
        state.string = "平常通り運行中"
    expected = item.get_text("\n", strip=True)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=str(soup)),
        )) as client:
            provider = HakoneTozanProvider(client=client)
            await provider.refresh()
            assert provider.main.status is LineStatus.UNKNOWN
            alert, = provider.alerts
            assert alert.description == expected
            assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
            assert not provider.delay_lines and not provider.affected_lines

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "missing_item", "duplicate_item",
    "missing_state", "duplicate_state", "empty_state", "dash_state", "wrong_name", "wrong_route",
])
def test_synthetic_malformed_source_preserves_previous_snapshot(mutation: str) -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    kind, target_name = mutation.split("_", 1)
    selector = {
        "panel": '[data-toggle-contents="operation"]', "item": '[data-code="T0001"]',
        "state": ".operation_state", "name": '[data-code="T0001"]', "route": '[data-code="T0001"]',
    }[target_name]
    target = _one(soup, selector)
    if kind == "missing":
        target.decompose()
    elif kind == "duplicate":
        target.insert_after(BeautifulSoup(str(target), "html.parser"))
    elif kind == "empty":
        target.clear()
    elif kind == "dash":
        target.string = "-"
    else:
        target["data-name" if target_name == "name" else "data-route-cd"] = "unrecognized"
    html = str(_synthetic_warning())

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html),
        )) as client:
            provider = HakoneTozanProvider(client=client)
            await provider.refresh()
            before = provider.lines
            html = str(soup)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is before

    asyncio.run(scenario())


def test_selection_injection_and_failure_isolation() -> None:
    paths: list[str] = []

    async def scenario() -> None:
        broken = False

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.host)
            if request.url.host == "www.hakonenavi.jp":
                if broken:
                    raise httpx.ConnectError("synthetic offline", request=request)
                return httpx.Response(200, text=_html())
            return httpx.Response(200, content=(_FIXTURES / "yuirail_normal.json").read_bytes())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = HakoneTozanProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert paths == [] and disabled.hakone_tozan is provider
            tracker = Tracker(enabled_providers=("hakone_tozan", "yuirail"), client=client, overrides=(provider,))
            assert tracker.providers[0] is provider
            await tracker.refresh()
            before = provider.lines
            broken = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {provider.provider_id}
            assert isinstance(captured.value.errors[provider.provider_id], FetchError)
            assert provider.lines is before and tracker.yuirail.main.status is LineStatus.NORMAL
            assert "hakone_tozan" in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())
