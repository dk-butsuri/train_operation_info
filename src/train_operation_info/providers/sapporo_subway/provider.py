"""Sapporo Municipal Subway's three official route notices.

Investigation: public HTML/JavaScript inspection on 2026-11-04 JST.
https://operationstatus.city.sapporo.jp/unkojoho/ returns server-rendered
div.line / h2.status records. The inline language selector navigates to
translated HTML; /shared/site_st/js/st_jsset.js handles presentation only.
The exact normal message is verified in the live HTML. All other notices
remain UNKNOWN with their original text: no abnormal status vocabulary or
stable prose template has been verified for this current-page layout.

The official /unkojoho/rireki_all.html shows real 2026-10-07 and 2026-10-29
delay/recovery records, but these history fields do not establish the markup
or labels on the current page. Wayback's old index.html query returned no
captures; broader old/current-domain CDX queries returned HTTP 503. Abnormal
current-page responses and their update timestamp format remain unverified.
Incident/recovery/malformed tests are synthetic, not captured incidents.

Runtime fetches only the current Japanese page. History, delay certificates,
streetcars, translations and other homepage news are excluded. No separate
long-term notice field was found in the inspected page; notices mixed into
route records are retained. NORMAL means the source's 10-minute threshold,
including anticipated delays, not absence of every service change.
No applicability field was verified: timing=UNKNOWN; updated_at=None.
Evidence and capture hashes: tests/fixtures/SAPPORO_SUBWAY.md and manifest.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import Comment, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, LINE_CATALOG, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://operationstatus.city.sapporo.jp/unkojoho/"
_ID: Final = ProviderId("sapporo_subway")
_NORMAL: Final = "現在、10分以上の遅れは発生していません。"
_ROUTES: Final = (
    ("南北線", LineId("jp:operator_8161169f094c:line_b55a3152dc18")),
    ("東西線", LineId("jp:operator_8161169f094c:line_efe2ab637efc")),
    ("東豊線", LineId("jp:operator_8161169f094c:line_cddc2da78846")),
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Sapporo Municipal Subway official",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Current Japanese notices for Namboku, Tozai and Toho lines",
    ),),
    terms_url=HttpUrl("https://www.city.sapporo.jp/city/copyright/link.html"),
    additional_terms_urls=(
        HttpUrl(_URL),
        HttpUrl("https://operationstatus.city.sapporo.jp/unkojoho/rireki_all.html"),
    ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The city copyright policy reserves private copying, quotation and other "
        "statutory uses and requires prior consultation for other copying/reuse. "
        "The linked history page additionally prohibits unauthorized content use, "
        "republication, distribution and publication. This is not a reuse licence. "
        "The current page publishes delays of 10 minutes or more, including anticipated delays."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-03T15:58:35+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Sapporo Subway element missing or duplicated: {selector}")
    return matches[0]


def _text(tag: Tag) -> str:
    clean = BeautifulSoup(str(tag), "html.parser")
    for hidden in clean.select("script, style, template, noscript"):
        hidden.decompose()
    return clean.get_text("\n", strip=True)


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    main = _one(soup, "#tmp_contents")
    if _text(_one(main, "h1.home")) != "運行情報":
        raise ParseError("Sapporo Subway page identity changed")
    headers = main.select("div.line")
    if len(headers) != len(_ROUTES) or len(main.select("h2.status")) != len(_ROUTES):
        raise ParseError("Sapporo Subway must contain three route/status records")
    # The first history link is a button; the second is in the common footer
    # notes. Use the latter to bound the last route without absorbing disclaimers.
    note_links = main.select('ul:not(.link_btn) > li > a[href="rireki_all.html"]')
    if len(note_links) != 1:
        raise ParseError("Sapporo Subway common notes boundary changed")
    notes = note_links[0].parent
    if not isinstance(notes, Tag) or not isinstance(notes.parent, Tag):
        raise ParseError("Sapporo Subway common notes missing")
    boundary = notes.parent
    if any(not isinstance(child, (Tag, Comment)) and str(child).strip() for child in main.children):
        raise ParseError("Sapporo Subway contains unstructured notice text")
    children = [child for child in main.children if isinstance(child, Tag)]
    if boundary.parent is not main or any(header.parent is not main for header in headers):
        raise ParseError("Sapporo Subway route record nesting changed")
    stop = children.index(boundary)
    by_name: dict[str, str] = {}
    for index, header in enumerate(headers):
        name = _text(header)
        if name not in dict(_ROUTES) or name in by_name:
            raise ParseError(f"Unexpected or duplicate Sapporo Subway route: {name}")
        start = children.index(header) + 1
        end = children.index(headers[index + 1]) if index + 1 < len(headers) else stop
        record = children[start:end]
        if start >= end or end > stop or record[0] not in main.select("h2.status"):
            raise ParseError(f"Sapporo Subway status missing for {name}")
        if not _text(record[0]):
            raise ParseError(f"Empty Sapporo Subway status: {name}")
        by_name[name] = "\n".join(text for tag in record if (text := _text(tag)))
    result: list[Line] = []
    for (name, identifier), line in zip(_ROUTES, lines):
        if line.line_id != identifier:
            raise ParseError("Sapporo Subway canonical route mismatch")
        body = by_name[name]
        status = LineStatus.NORMAL if body == _NORMAL else LineStatus.UNKNOWN
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{name} 運行情報", body),
        )
        result.append(snapshot(
            line, status, body, fetched_at, alerts=alerts, source_line_names=(name,),
        ))
    return tuple(result)


class SapporoSubwayProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL) for _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content.decode("utf-8-sig"), self.lines, self._now())

    @property
    def namboku(self) -> Line:
        return self._line("line_b55a3152dc18")

    @property
    def tozai(self) -> Line:
        return self._line("line_efe2ab637efc")

    @property
    def toho(self) -> Line:
        return self._line("line_cddc2da78846")
