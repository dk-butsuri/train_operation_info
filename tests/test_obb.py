"""Real ÖBB incident/empty-list captures and explicitly synthetic mutations."""

import asyncio
from pathlib import Path

from bs4 import BeautifulSoup
import httpx
import pytest

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineScope, LineStatus
from train_operation_info.providers.obb import ObbProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.unsereoebb.at/verkehrsmeldungen"


def _html(name: str = "20260717055055") -> bytes:
    return (_FIXTURES / f"obb_{name}.html").read_bytes()


@pytest.mark.parametrize(("capture", "count", "fragment"), [
    ("20260314200213", 1, "kurzfristige Bauarbeiten"),
    ("20260717055055", 2, "Bis 07:36 Uhr war"),
])
def test_archived_incident_categories_do_not_infer_effect_or_applicability(
    capture: str, count: int, fragment: str,
) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == _URL and request.method == "GET"
            return httpx.Response(200, content=_html(capture))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ObbProvider(client=client)
            assert provider.network.status is LineStatus.UNKNOWN
            await provider.refresh()
            assert len(provider.lines) == 1
            line = provider.network
            assert line.line_id == LineId("at:obb:network")
            assert line.scope is LineScope.GROUP
            assert line.operator.name == "ÖBB"
            assert line.status is LineStatus.UNKNOWN and line.updated_at is None
            assert line.fetched_at is not None and line.fetched_at.utcoffset() is not None
            assert len(provider.alerts) == count
            assert fragment in "\n".join(a.description for a in provider.alerts)
            for alert in provider.alerts:
                assert alert.effect is AlertEffect.OTHER
                assert alert.timing is AlertTiming.UNKNOWN
                assert alert.affected_line_ids == () and alert.language == "de"
                assert alert.source_url.startswith("https://www.unsereoebb.at/de/verkehrsmeldungen~")
                assert alert.active_from is None and alert.active_until is None
            assert not provider.active_alerts and not provider.affected_lines
            assert provider.unclassified_alerts == provider.alerts
            assert not client.is_closed

    asyncio.run(scenario())


def test_real_later_empty_incident_list_clears_old_alerts_but_ignores_construction() -> None:
    html = _html()

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = ObbProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.network
            assert len(previous.alerts) == 2
            html = _html("no_incidents_20261103")
            await provider.refresh()
            assert provider.network.status is LineStatus.NORMAL
            assert not provider.alerts
            assert len(previous.alerts) == 2  # immutable previous snapshot
            assert "Wien Stammstrecke" in html.decode("utf-8")

    asyncio.run(scenario())


def test_synthetic_unknown_category_is_retained_without_narrative_classification() -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    first = soup.select_one('.traffic-news__item[data-infotype="streckeninfo"]')
    assert first is not None
    first["data-infotype"] = "new-category"
    label = first.select_one(".traffic-news__infotype")
    assert label is not None
    label.string = "Synthetic new category"
    description = first.select_one(".traffic-news__description")
    assert description is not None
    description.string = "Synthetic quotation: no trains tomorrow; delay ended yesterday."

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=str(soup).encode("utf-8")),
        )) as client:
            provider = ObbProvider(client=client)
            await provider.refresh()
            alert = provider.alerts[0]
            assert alert.effect is AlertEffect.UNKNOWN
            assert alert.timing is AlertTiming.UNKNOWN and alert.affected_line_ids == ()
            assert alert.description == description.get_text()
            assert provider.network.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", [
    "missing_overview", "duplicate_overview", "outside_item", "missing_legend",
    "changed_legend", "missing_type", "missing_title", "empty_body",
    "external_url", "duplicate_incident", "wrong_category_label",
])
def test_synthetic_malformed_source_preserves_previous_snapshot(mutation: str) -> None:
    soup = BeautifulSoup(_html(), "html.parser")
    panel = soup.select_one(".traffic-news__overview")
    item = soup.select_one('.traffic-news__item[data-infotype="streckeninfo"]')
    assert panel is not None and item is not None
    if mutation == "missing_overview":
        panel.decompose()
    elif mutation == "duplicate_overview":
        panel.insert_after(BeautifulSoup(str(panel), "html.parser"))
    elif mutation == "outside_item":
        soup.append(item.extract())
    elif mutation == "missing_legend":
        legend = soup.select_one("#infoTypeFilterButtons")
        assert legend is not None
        legend.decompose()
    elif mutation == "changed_legend":
        button = soup.select_one('button[data-value="streckeninfo"]')
        assert button is not None
        button.string = "Different meaning"
    elif mutation == "missing_type":
        del item["data-infotype"]
    elif mutation == "missing_title":
        title = item.select_one("h2")
        assert title is not None
        title.decompose()
    elif mutation == "empty_body":
        body = item.select_one(".traffic-news__description")
        assert body is not None
        body.clear()
    elif mutation == "external_url":
        link = item.select_one("h2 a")
        assert link is not None
        link["href"] = "https://example.com/other-source"
    elif mutation == "duplicate_incident":
        item.insert_after(BeautifulSoup(str(item), "html.parser"))
    else:
        label = item.select_one(".traffic-news__infotype")
        assert label is not None
        label.string = "Baustelle"
    html = _html()

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = ObbProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.lines
            html = str(soup).encode("utf-8")
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_out_of_scope_construction_payload_is_not_validated() -> None:
    soup = BeautifulSoup(_html("no_incidents_20261103"), "html.parser")
    for item in soup.select('.traffic-news__item[data-infotype="baustelle"]'):
        item.clear()
        item.string = "Synthetic broken out-of-scope construction data"

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=str(soup).encode("utf-8")),
        )) as client:
            provider = ObbProvider(client=client)
            await provider.refresh()
            assert provider.network.status is LineStatus.NORMAL and not provider.alerts

    asyncio.run(scenario())


def test_http_failure_keeps_previous_snapshot() -> None:
    fail = False

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(503 if fail else 200, content=_html()),
        )) as client:
            provider = ObbProvider(client=client)
            provider.rate_limit = 0
            await provider.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())
