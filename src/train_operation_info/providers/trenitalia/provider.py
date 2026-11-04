"""Trenitalia's official national Infomobilita notice board (Italian).

Investigation: archived official HTML and public HTML/JavaScript, 2026-11-04.
Source: https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html
The full national regular-traffic bulletin has identical title/body wording in
https://web.archive.org/web/20240102054440id_/https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html
and the current-layout normal capture at
https://web.archive.org/web/20260101154916id_/https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html
Only that complete, Informazione-category bulletin establishes NORMAL for the
national GROUP. It describes network traffic, not each train's punctuality.
The live 2026-11-04 bulletin covers only Alta Velocita: it cannot establish
national normality. No title substring, cause, date or colour class is used
to infer delay, cancellation, an affected route or ACTIVE timing. Green means
Informazione and also labels works; red Attenzione also labels recovered
incidents. Other in-scope notices are OTHER alerts, network status UNKNOWN
unless the verified national bulletin is present. Its presence does not erase
other notices (the normal capture also retains warning and works notices).

The official clientlib-site script's Infomobility class only filters by region
and opens accordions; the complete board is embedded in HTML without paging.
Programmazione-category notices are structurally separate planned information
and excluded. Works classified Informazione remain mixed into the board and
are retained without prose filtering. Raw captures contain excluded notices.
Dates are publication days, not aware update timestamps or applicability
bounds: updated_at/active_from/active_until stay None; timing stays UNKNOWN.
Source category/day, title and body text are retained. Train searches, linked
PDFs/details and the legacy layout are outside scope. ViaggiaTreno returned
403 with the identifying library User-Agent and is not accessed at runtime.

Evidence, UTC retrieval times and hashes: tests/fixtures/TRENITALIA.md and
trenitalia_manifest.json. Real normal and abnormal HTML are tested; recovery,
malformation and refusal tests are synthetic. Terms allow personal saving
but require prior permission for redistribution: explicit opt-in only.
"""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html"
_ID: Final = ProviderId("trenitalia")
_NORMAL_TITLE: Final = "CIRCOLAZIONE REGOLARE"
# Complete fixed bulletin, independently confirmed in the 2024 and 2026 archives.
_NORMAL_BODY: Final = (
    "In questo momento la circolazione si svolge regolarmente su tutta la rete ferroviaria nazionale. "
    "Eventuali ritardi registrati si riferiscono a precedenti inconvenienti già risolti. "
    "REGULAR RAILWAY TRAFFIC "
    "At the moment, the railway traffic is regular on the whole national network. "
    "Possible registered delays refer to previous service inconveniences that have been already solved."
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Trenitalia official Infomobilita",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Complete embedded national notice board; Programmazione category excluded.",
    ),),
    terms_url=HttpUrl(
        "https://www.trenitalia.com/it/informazioni/termini-e-condizioni-di-utilizzo-sito-trenitalia.html"
    ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "Terms permit saving individual extracts for strictly personal noncommercial use; "
        "reproduction, transfer, publication and distribution require prior express consent. "
        "Use of content on another site, server or networked environment is restricted. "
        "Explicit opt-in only; users must check terms and obtain required permission. "
        "Covers national traffic bulletins, not individual train punctuality or route statuses."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T11:55:48.813721+00:00"),
)


def _one(node: Tag | BeautifulSoup, selector: str) -> Tag:
    matches = node.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Trenitalia required element missing or duplicated: {selector}")
    return matches[0]


def _text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def _parse(html: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    board = _one(soup, "#infomobility-page main .infomobility-list .body-infomobility")
    notices = board.select(":scope > .infomobility")
    if not notices or len(notices) != len(board.select(".infomobility")):
        raise ParseError("Trenitalia notice board empty or unexpectedly nested")
    identifiers: set[str] = set()
    alerts: list[ServiceAlert] = []
    normal = False
    for notice in notices:
        identifier = notice.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ParseError("Trenitalia notice ID missing or duplicated")
        identifiers.add(identifier)
        category = _text(_one(notice, ".infomobility-text .visually-hidden"))
        if not category:
            raise ParseError("Trenitalia notice category empty")
        if category == "Programmazione":
            # Its payload is outside scope, including its validation.
            continue
        title = _text(_one(notice, "h3.infomobility-title"))
        day = _text(_one(notice, ".infomobility-date"))
        body_node = _one(notice, ".accordion-body .description.richtext")
        body = _text(body_node)
        if not title or not body:
            raise ParseError("Trenitalia notice title or body empty")
        # Validate the published day but never invent a midnight timestamp.
        if datetime.strptime(day, "%d/%m/%Y").strftime("%d/%m/%Y") != day:
            raise ParseError("Trenitalia publication day format changed")
        if (
            category == "Informazione" and title == _NORMAL_TITLE and body == _NORMAL_BODY
            and len(body_node.find_all("p", recursive=False)) == 5
            and body_node.find_parent("blockquote") is None
            and all(tag.name in ("p", "b", "i", "br") for tag in body_node.select("*"))
        ):
            if normal:
                raise ParseError("Trenitalia national normal bulletin duplicated")
            normal = True
            continue
        alerts.append(make_alert(
            line, LineStatus.ALERT, title,
            f"{category} — {day}\n\n{body_node.get_text(chr(10), strip=True)}",
            alert_id="trenitalia:" + sha256(identifier.encode()).hexdigest()[:24],
            affected_line_ids=(), language="it",
        ))
    return (snapshot(
        line, LineStatus.NORMAL if normal else LineStatus.UNKNOWN,
        _NORMAL_TITLE if normal else "Notizie Infomobilità", fetched_at,
        alerts=tuple(alerts),
    ),)


class TrenitaliaProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__((
            LINE_CATALOG[LineId("it:trenitalia:network")].create_line(_ID, _URL),
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.network, self._now())

    @property
    def network(self) -> Line:
        return self._line("network")
