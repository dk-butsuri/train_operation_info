"""Sendai City Transportation Bureau's two official subway notice pages.

Investigation: public HTML/CSS/JavaScript inspection and Wayback CDX queries,
2026-11-04 UTC. Current pages /unkou/nanbokusen/ and /unkou/touzaisen/
on https://www.kotsu.city.sendai.jp/ contain server-rendered route records.
/unkou/ documents the 30-minute actual/anticipated delay reporting threshold.
The public theme's css/unkou.css defines ope_normal, ope_down and ope_lag
icons and .unkou_detail_text; js/navigation.js controls menus, not a feed.
Neither CSS class names nor narrative words establish disruption scope or
applicability. Only the observed ope_normal + exact complete 平常運行 record
maps to NORMAL; other notices remain UNKNOWN with their text and links.
Wayback 20260412141736id_/https://www.kotsu.city.sendai.jp/unkou/touzaisen/
and 20260712033444id_/https://www.kotsu.city.sendai.jp/unkou/ show normal
records in the current layout. No abnormal current-layout response has been verified.
CDX results and exact
query URLs, capture times and hashes are recorded in SENDAI_SUBWAY.md's
companion manifest. Incident/recovery/malformed tests are explicitly synthetic.

Runtime fetches both Japanese route pages, including detail text in page_inner.
Certificate buttons are structurally excluded. Certificates, news, bus notices,
timetables, X and linked articles are not fetched. No separate long-term field
was verified; mixed route notices are retained. NORMAL is limited to the
source's reporting threshold. timing=UNKNOWN; updated_at/active periods=None:
WordPress page modification dates are not route-status update timestamps.
Missing/duplicate route/status structures fail without replacing the snapshot.
Evidence: tests/fixtures/SENDAI_SUBWAY.md and sendai_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_ROOT: Final = "https://www.kotsu.city.sendai.jp"
_URL: Final = f"{_ROOT}/unkou/"
_ID: Final = ProviderId("sendai_subway")
_NORMAL: Final = "平常運行"
_ROUTES: Final = (
    ("nanbokusen", "南北線", LineId("jp:operator_31739cacf719:line_cc1ac570adb3")),
    ("touzaisen", "東西線", LineId("jp:operator_31739cacf719:line_3cb65ac614ea")),
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Sendai City Subway official", source_page_url=HttpUrl(_URL),
    endpoints=tuple(SourceEndpoint(
        url=f"{_URL}{key}/", method="GET", format=DataFormat.HTML,
        description=f"Current Japanese {name} notice and in-page details; certificates excluded",
    ) for key, name, _ in _ROUTES),
    terms_url=HttpUrl(f"{_ROOT}/menseki/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The bureau's copyright policy prohibits unauthorized copying/reuse except "
        "private copying, quotation and other statutory uses; it grants no reuse licence. "
        "Its link policy requests consultation for pages other than the homepage. "
        "Subway notices cover delays of 30 minutes or more, including anticipated delays."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:11:34+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Sendai Subway element missing or duplicated: {selector}")
    return matches[0]


def _parse(html: str, key: str, name: str, line: Line, fetched_at: datetime) -> Line:
    soup = BeautifulSoup(html, "html.parser")
    main = _one(soup, "#mainarea .page_contents")
    if _one(main, "h2").get_text(strip=True) != "運行情報":
        raise ParseError("Sendai Subway page identity changed")
    inner = _one(main, ".page_inner")
    box = _one(inner, f"div#{key}.{key}_unkou_box")
    if len(inner.select("div.nanbokusen_unkou_box, div.touzaisen_unkou_box")) != 1:
        raise ParseError("Sendai Subway route record duplicated")
    record = _one(box, "dl")
    heading = _one(record, "dt")
    if heading.get_text(strip=True) != f"地下鉄{name}":
        raise ParseError("Sendai Subway route identity changed")
    status_field = _one(record, "dd")
    if not status_field.get_text(strip=True):
        raise ParseError("Sendai Subway status is empty")
    normal_code = set(status_field.get_attribute_list("class")) == {"clearfix", "ope_normal"}
    # Keep the entire route page's content, including detail blocks beside the box.
    # Only the verified certificate-button region and the route heading are removed.
    heading.decompose()
    for certificate in inner.select(".chien_btn"):
        certificate.decompose()
    if inner.select("script, style, iframe, template, noscript"):
        raise ParseError("Unexpected executable Sendai Subway notice content")
    for image in inner.select("img"):
        alt = image.get("alt")
        if not isinstance(alt, str) or not alt.strip():
            raise ParseError("Sendai Subway notice image has no alternative text")
        image.replace_with(NavigableString(alt))
    body = inner.get_text("\n", strip=True)
    links: list[str] = []
    for link in inner.select("a"):
        href = link.get("href")
        if not isinstance(href, str) or not href.strip():
            raise ParseError("Sendai Subway notice link has no destination")
        target = urljoin(str(line.source_url), href)
        HttpUrl(target)
        links.append(target)
    description = "\n".join((body, *dict.fromkeys(links)))
    status = LineStatus.NORMAL if normal_code and description == _NORMAL else LineStatus.UNKNOWN
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, f"{name} 運行情報", description),
    )
    return snapshot(line, status, description, fetched_at, alerts=alerts, source_line_names=(name,))


class SendaiSubwayProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, f"{_URL}{key}/")
            for key, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        pages: list[str] = []
        for key, _, _ in _ROUTES:
            response = await self._get(client, f"{_URL}{key}/")
            response.raise_for_status()
            pages.append(response.content.decode("utf-8-sig"))
        fetched_at = self._now()
        return tuple(
            _parse(html, key, name, line, fetched_at)
            for html, (key, name, _), line in zip(pages, _ROUTES, self.lines)
        )

    @property
    def namboku(self) -> Line:
        return self._line("line_cc1ac570adb3")

    @property
    def tozai(self) -> Line:
        return self._line("line_3cb65ac614ea")
