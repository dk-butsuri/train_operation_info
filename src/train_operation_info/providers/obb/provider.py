"""ÖBB's editorial network incident notices, not individual train punctuality.

Investigation: public official HTML/JavaScript and archived official HTML.
https://infrastruktur.oebb.at/de/unternehmen/kundinnen-im-mittelpunkt/kundeninformation/vor-der-reise/info-zu-stoerungen-vor-reise
links to https://www.unsereoebb.at/verkehrsmeldungen. Its server-rendered
.traffic-news__overview contains all published items. The official script
https://www.unsereoebb.at/.resources/rcg-2019/themes/js/site.min~2026-10-27-13-29-25-000~cache.js
filters these existing items by data-infotype: the page labels streckeninfo
as Störfall and baustelle as Baustelle. No pagination or load-more is used.
The script also constructs an incident-only RSS URL; its empty live channel
corroborated the live HTML's absence of incident items on 2026-11-03 UTC.

Unmodified archived originals:
https://web.archive.org/web/20260314200213id_/https://www.unsereoebb.at/de/verkehrsmeldungen
has a streckeninfo notice published before its announced restrictions; the capture at
https://web.archive.org/web/20260717055055id_/https://www.unsereoebb.at/de/verkehrsmeldungen
has both current restrictions and a notice explicitly describing a finished
incident in the same category. Category therefore establishes only a notice,
not DELAYED/SUSPENDED, current applicability or a validity interval. All
incident prose is retained, timing UNKNOWN, active_from/active_until None.
The displayed local date labels have no explicit timezone; updated_at is None.

Only this editorial incident list is covered. Structurally separate baustelle
items are ignored without validating their payload; their bytes remain in the
HTTP capture. Long-duration material inside streckeninfo is retained. SCOTTY,
station boards, train-level delays and linked construction articles are not
queried. NORMAL means no incident items in this published list, not that the
whole railway is running normally. The single canonical GROUP is the ÖBB
network, not a synthetic individual route. Incident endpoints in free text
are not mapped to lines: affected_line_ids=(), network status UNKNOWN while
notices exist, with OTHER alerts for the verified incident category. Unknown
categories are retained as UNKNOWN alerts. Missing identity/structure raises
ParseError and preserves the previous snapshot. Evidence and extraction,
UTC retrieval times, hashes and limitations: tests/fixtures/OBB.md and
obb_manifest.json. Unknown/malformed cases are explicitly synthetic tests.
"""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.unsereoebb.at/verkehrsmeldungen"
_ID: Final = ProviderId("obb")
_LINE_ID: Final = LineId("at:obb:network")
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="ÖBB official network incident notices",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description=(
            "Server-rendered editorial traffic list; only incident items "
            "(data-infotype=streckeninfo), excluding separate baustelle items. "
            "Other categories remain unclassified notices."
        ),
    ),),
    terms_url=HttpUrl("https://holding.oebb.at/de/nutzungsbedingungen"),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The linked ÖBB-Holding website terms, section 3, reserve copyright, "
        "limit content to personal noncommercial use and require prior written "
        "permission for reproduction, modification or distribution and other "
        "use beyond the granted rights. No separate traffic-data reuse grant "
        "was found. Public accessibility and an RSS feed are not a reuse licence. "
        "Only editorial incident notices are covered; no train-level service "
        "or all-network punctuality guarantee."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:36:08.163456+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"ÖBB element missing or duplicated: {selector}")
    return matches[0]


def _parse(html: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    main = _one(soup, "main")
    filters = _one(main, "#infoTypeFilterButtons")
    for value, label in (("baustelle", "Baustelle"), ("streckeninfo", "Störfall")):
        button = _one(filters, f'button[data-value="{value}"]')
        if button.get_text(" ", strip=True) != label:
            raise ParseError("ÖBB incident type legend changed")
    panel = _one(main, ".traffic-news__wrapper.traffic-news__overview")
    items = panel.select(":scope > .traffic-news__item")
    if len(items) != len(soup.select(".traffic-news__item")):
        raise ParseError("ÖBB incident item outside the complete overview")
    alerts: list[ServiceAlert] = []
    identifiers: set[str] = set()
    source_types: set[str] = set()
    for item in items:
        category = item.get("data-infotype")
        if not isinstance(category, str) or not category.strip():
            raise ParseError("ÖBB incident type missing")
        if category == "baustelle":
            continue
        title_node = _one(item, ".traffic-news__header h2 a")
        title = title_node.get_text(" ", strip=True)
        href = title_node.get("href")
        if not title or not isinstance(href, str):
            raise ParseError("ÖBB incident title or URL missing")
        url = HttpUrl(href)
        if urlsplit(str(url)).hostname != "www.unsereoebb.at":
            raise ParseError("ÖBB incident URL host changed")
        identifier = sha256(f"obb:{href}".encode()).hexdigest()[:24]
        if identifier in identifiers:
            raise ParseError("ÖBB incident duplicated")
        identifiers.add(identifier)
        label = _one(item, ".traffic-news__infotype").get_text(" ", strip=True)
        if not label:
            raise ParseError("ÖBB incident category label empty")
        if category == "streckeninfo" and label != "Störfall aus der Verkehrsleitzentrale":
            raise ParseError("ÖBB incident category and label disagree")
        body_node = _one(item, ".traffic-news__description")
        for hidden in body_node.select("script, style, template, noscript"):
            hidden.decompose()
        body = body_node.get_text("\n", strip=True)
        if not body:
            raise ParseError("ÖBB incident description empty")
        status = LineStatus.ALERT if category == "streckeninfo" else LineStatus.UNKNOWN
        alert = make_alert(
            line, status, title, body, alert_id=identifier,
            affected_line_ids=(), language="de",
        )
        alerts.append(ServiceAlert.model_validate({**alert.model_dump(), "source_url": str(url)}))
        source_types.add(label)
    state = LineStatus.UNKNOWN if alerts else LineStatus.NORMAL
    source_status = " | ".join(sorted(source_types)) if alerts else "No published incident notices"
    return (snapshot(line, state, source_status, fetched_at, alerts=tuple(alerts)),)


class ObbProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE_ID].create_line(_ID, _URL),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.network, self._now())

    @property
    def network(self) -> Line:
        return self.lines[0]
