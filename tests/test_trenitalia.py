"""Official live/archived HTML and explicitly synthetic parser/failure cases."""

import asyncio
from hashlib import sha256
import json
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineId, LineScope, LineStatus
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.trenitalia import TrenitaliaProvider

_URL = "https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html"
_FIXTURES = Path(__file__).parent / "fixtures"


def _notice(
    *, identifier: str = "SYNTHETIC", category: str = "Attenzione",
    title: str = "Synthetic notice", body: str = "Synthetic passenger information.",
    day: str = "04/11/2026",
) -> str:
    return (
        f'<div class="infomobility" id="{identifier}"><div class="infomobility-text">'
        f'<span class="visually-hidden">{category}</span>'
        f'<h3 class="infomobility-title">{title}</h3>'
        f'<p class="infomobility-date">{day}</p></div>'
        f'<div class="accordion-body"><div class="description richtext"><p>{body}</p></div></div></div>'
    )


def _page(*notices: str) -> bytes:
    return (
        '<div id="infomobility-page"><main><div class="infomobility-list">'
        '<div class="body-infomobility">' + "".join(notices) + '</div></div></main></div>'
    ).encode()


def _capture(name: str) -> bytes:
    data = (_FIXTURES / name).read_bytes()
    manifest = json.loads((_FIXTURES / "trenitalia_manifest.json").read_text(encoding="utf-8"))
    entry, = [d for d in manifest["documents"] if d.get("fixture") == name]
    assert sha256(data).hexdigest() == entry["original_sha256"]
    return data


def test_official_live_capture_keeps_high_speed_normal_separate_from_national_state() -> None:
    html = _capture("trenitalia_live_20261104.html")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            tracker = Tracker(enabled_providers=("trenitalia",), client=client)
            await tracker.refresh()
            line = tracker.trenitalia.network
            assert line.line_id == LineId("it:trenitalia:network")
            assert line.scope is LineScope.GROUP and line.operator.name == "Trenitalia"
            assert line.status is LineStatus.UNKNOWN
            assert line.updated_at is None and line.fetched_at is not None
            assert len(line.alerts) == 26  # 28 published; two Programmazione notices excluded.
            assert any("ALTA VELOCITÀ" in a.title for a in line.alerts)
            assert any(a.title.startswith("INFOLAVORI") for a in line.alerts)
            assert any("sospesa" in a.title for a in line.alerts)
            assert not client.is_closed
            for alert in line.alerts:
                assert alert.effect is AlertEffect.OTHER and alert.timing is AlertTiming.UNKNOWN
                assert alert.affected_line_ids == () and alert.language == "it"
                assert alert.active_from is None and alert.active_until is None
                assert alert.title and alert.description and alert.source_url == _URL

    asyncio.run(scenario())


def test_archived_national_normal_and_live_abnormal_recovery_keep_other_notices() -> None:
    normal = _capture("trenitalia_normal_20260101154916.html")
    abnormal = _capture("trenitalia_live_20261104.html")
    html = abnormal

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = TrenitaliaProvider(client=client)
            for document, expected, count in [
                (abnormal, LineStatus.UNKNOWN, 26), (normal, LineStatus.NORMAL, 23),
                (abnormal, LineStatus.UNKNOWN, 26), (normal, LineStatus.NORMAL, 23),
            ]:
                html = document
                await provider.refresh()
                assert provider.network.status is expected
                assert len(provider.alerts) == count
                assert provider.network.updated_at is None
                assert not provider.active_alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [
    "circolazione sospesa", "circolazione rallentata", "circolazione regolare",
    "La circolazione non è sospesa.", "Domani la circolazione sarà sospesa.",
    "Testo citato: CIRCOLAZIONE REGOLARE. Non è una dichiarazione attuale.",
])
@pytest.mark.parametrize("category", ["Attenzione", "Informazione", "New category"])
def test_synthetic_narrative_and_categories_do_not_infer_status(body: str, category: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_page(_notice(
                category=category, title="CIRCOLAZIONE REGOLARE", body=body,
            ))),
        )) as client:
            provider = TrenitaliaProvider(client=client)
            await provider.refresh()
            assert provider.network.status is LineStatus.UNKNOWN
            assert provider.alerts[0].effect is AlertEffect.OTHER
            assert body in provider.alerts[0].description
            assert category in provider.alerts[0].description
            assert provider.alerts[0].affected_line_ids == ()

    asyncio.run(scenario())


def test_synthetic_removed_notices_clear_and_planned_payload_is_not_consumed() -> None:
    html = _page(_notice())

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = TrenitaliaProvider(client=client)
            await provider.refresh()
            assert len(provider.alerts) == 1
            html = _page(_notice(category="Programmazione", title="", body="", day="bad"))
            await provider.refresh()
            cleared = provider.network
            assert not cleared.alerts
            assert cleared.status is LineStatus.UNKNOWN

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["quote", "append", "negate", "future", "scope", "category", "title"])
def test_mutated_normal_bulletin_never_establishes_national_normality(mutation: str) -> None:
    soup = BeautifulSoup(_capture("trenitalia_normal_20260101154916.html"), "html.parser")
    notice = soup.select_one('.infomobility[id="CIRCOLAZIONE_REGOLARE"]')
    assert notice is not None
    body = notice.select_one(".description.richtext")
    title = notice.select_one(".infomobility-title")
    category = notice.select_one(".visually-hidden")
    assert body is not None and title is not None and category is not None
    if mutation == "quote":
        body.wrap(soup.new_tag("blockquote"))
        # Quoting inside the body also preserves visible text; it is not a bulletin.
        for paragraph in body.select("p"):
            paragraph.wrap(soup.new_tag("blockquote"))
    elif mutation == "append":
        body.append("Synthetic extra information: not a confirmed normal bulletin.")
    elif mutation in ("negate", "future", "scope"):
        first_paragraph = body.select_one("p")
        assert first_paragraph is not None
        first_paragraph.string = {
            "negate": "In questo momento la circolazione non si svolge regolarmente su tutta la rete ferroviaria nazionale.",
            "future": "Domani la circolazione si svolgerà regolarmente su tutta la rete ferroviaria nazionale.",
            "scope": "In questo momento la circolazione si svolge regolarmente sull'intera rete Alta Velocità.",
        }[mutation]
    elif mutation == "category":
        category.string = "Attenzione"
    else:
        title.string = 'Citazione: "CIRCOLAZIONE REGOLARE"'
    html = str(soup).encode()

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = TrenitaliaProvider(client=client)
            await provider.refresh()
            assert provider.network.status is LineStatus.UNKNOWN
            assert len(provider.alerts) == 24

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [
    b"maintenance page", _page(), _page(_notice(), _notice()),
    _page(_notice(title="")), _page(_notice(body="")), _page(_notice(category="")),
    _page(_notice(day="31/02/2026")), _page(_notice(day="2026-11-04")),
    _page(_notice()).replace(b'infomobility-date', b'missing-date'),
    _page(_notice()).replace(b'class="visually-hidden"', b'class="missing-category"'),
    _page(_notice()).replace(b'id="SYNTHETIC"', b'id=""'),
    _page(_notice()).replace(b'<h3 class=', b'<h3></h3><h3 class=').replace(
        b'<h3></h3>', b'<h3 class="infomobility-title">Duplicate</h3>',
    ),
])
def test_synthetic_malformed_response_keeps_previous_snapshot(bad: bytes) -> None:
    html = _page(_notice())

    async def scenario() -> None:
        nonlocal html
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=html),
        )) as client:
            provider = TrenitaliaProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            html = bad
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [403, 429, 503])
def test_synthetic_refusals_are_not_retried_and_use_identifying_agent(status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == _URL
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(status, text="Synthetic refusal")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TrenitaliaProvider(client=client)
            previous = provider.lines
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous
        assert len(requests) == 1

    asyncio.run(scenario())
