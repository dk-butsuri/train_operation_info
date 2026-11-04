"""Nishitetsu's official emergency operation notices.

Investigation: public HTML/JavaScript and Wayback archives, 2026-11-04 UTC.
https://www.nishitetsu.jp/train/ links #Trafficlink to
https://jik.nishitetsu.jp/traffic/default.htm. /traffic/top_inc.js changes
the link's summary only; the HTML contains the full notices in div.traffic.
Archived default.htm responses 20240829221823 and 20260728135357 contain
railway and bus notices as h3/p pairs. The exact railway headings below
identify the Tenjin-Omuta group (including Dazaifu and Amagi) and Kaizuka.
20240124024435 contains a restoration notice in the same railway group:
publication does not establish an ongoing disruption. Thus each published
railway notice yields ALERT, never a disruption class or timing=ACTIVE.
Group alerts have affected_line_ids=(): the heading identifies the publication
scope, not which individual lines are affected. Kaizuka's heading is specific.

20241003190025 and live HTML contain the same complete no-notice paragraph;
20260817152210 contains only a bus notice. NORMAL means no railway notice
published in this emergency panel, not proof of normal service or absence of
minor delays. Unrecognized headings are retained with UNKNOWN on all four
lines and affected_line_ids=(); they are never silently treated as buses.
Known bus headings are excluded structurally. Blank, duplicate or malformed
panels/pairs raise ParseError; no partial snapshot is committed.

The notices include yearless '現在' timestamps, free prose, recovery and plans.
updated_at/active_from/active_until remain None and timing remains UNKNOWN.
No structural long-term category was verified within the railway panel; all
railway notices there are retained. Separate site news, X, linked articles,
certificates, positions and bus feeds are not fetched. Raw response recordings
can include the excluded bus notices and external-site link table.
Real normal, railway disruption/recovery and bus-only captures test parsing;
unknown headings, malformed pages and clearing sequences are synthetic.
Evidence and hashes: tests/fixtures/NISHITETSU.md, nishitetsu_manifest.json.
"""

from datetime import datetime
from html import escape
from pathlib import Path
import re
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://jik.nishitetsu.jp/traffic/default.htm"
_ID: Final = ProviderId("nishitetsu")
_ROUTES: Final = tuple(LineId("jp:operator_7b911b6ce6c0:" + key) for key in (
    "line_4e3d73d92dac", "line_ab3438d1ea2b", "line_18c851797e51", "line_872659be7aa0",
))
_GROUP: Final = "天神大牟田線（太宰府線・甘木線含む）"
_BUS_HEADINGS: Final = frozenset({"高速バス", "一般路線バス"})
_EMPTY: Final = "台風や大雪などの時に当社バス・電車の運行状況をお知らせいたします。"
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Nishitetsu official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Railway h3/p notices in div.traffic; bus notices and linked pages excluded",
    ),),
    terms_url=HttpUrl("https://www.nishitetsu.jp/nnr/site-kitei/"),
    additional_terms_urls=(HttpUrl("https://www.nishitetsu.jp/train/"),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site terms explicitly cover jik.nishitetsu.jp and prohibit reuse "
        "beyond private use or legally permitted use without prior permission. "
        "NORMAL means no railway notice in the emergency panel only. Railway "
        "notices can announce recovery or future plans; no impact or timing is "
        "inferred. Bus notices can be present in raw HTTP recordings."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T04:54:34+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Nishitetsu element missing or duplicated: {selector}")
    return matches[0]


def _notices(payload: bytes) -> tuple[tuple[str, str], ...]:
    # The source uses literal Japanese <...> labels inside p, which HTML parsers
    # otherwise turn into unknown elements and erase. Escape these non-ASCII
    # pseudo-tags only; this is text preservation, never status classification.
    html = re.sub(r"<[^\x00-\x7f][^<>]*>", lambda m: escape(m[0]), payload.decode("utf-8-sig"))
    soup = BeautifulSoup(html, "html.parser")
    if _one(soup, 'img[src="tit_unkou.jpg"]').get("alt") != "運行状況":
        raise ParseError("Unexpected Nishitetsu page heading")
    panel = _one(soup, "div.traffic")
    # Validate the following standing link table too, to reject truncated pages.
    if panel.find_next("table") is None or soup.body is None:
        raise ParseError("Nishitetsu page is incomplete")
    nodes = [n for n in panel.children if not isinstance(n, Comment) and str(n).strip()
             and not (isinstance(n, Tag) and n.name == "br")]
    if len(nodes) == 1 and type(nodes[0]) is NavigableString and str(nodes[0]).strip() == _EMPTY:
        return ()
    if not nodes or len(nodes) % 2:
        raise ParseError("Nishitetsu notice pairs missing or malformed")
    notices: list[tuple[str, str]] = []
    for index in range(0, len(nodes), 2):
        heading, body = nodes[index:index + 2]
        if (not isinstance(heading, Tag) or heading.name != "h3"
                or not isinstance(body, Tag) or body.name != "p"):
            raise ParseError("Unexpected Nishitetsu notice structure")
        title = heading.get_text(" ", strip=True)
        if title in _BUS_HEADINGS:
            continue  # Bus bodies and their links are outside the railway scope.
        if heading.select("script, style, iframe, template") or body.select("script, style, iframe, template, h3, p"):
            raise ParseError("Unexpected Nishitetsu notice content")
        text = body.get_text("\n", strip=True)
        if not title or not text or any(title == old for old, _ in notices):
            raise ParseError("Empty or duplicated Nishitetsu notice")
        links: list[str] = []
        for link in body.select("a"):
            href = link.get("href")
            if not isinstance(href, str) or not href.strip():
                raise ParseError("Nishitetsu notice link missing destination")
            target = urljoin(_URL, href)
            HttpUrl(target)
            links.append(target)
        notices.append((title, "\n".join((text, *dict.fromkeys(links)))))
    return tuple(notices)


class NishitetsuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[key].create_line(_ID, _URL) for key in _ROUTES),
                         client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        notices = _notices(response.content)
        alerts: dict[LineId, list[ServiceAlert]] = {line.line_id: [] for line in self.lines}
        unknown = False
        for title, text in notices:
            affected: tuple[LineId, ...]
            if title == _GROUP:
                targets, affected = self.lines[:3], ()
            elif title == "貝塚線":
                targets, affected = (self.kaizuka,), (self.kaizuka.line_id,)
            else:
                unknown = True
                targets, affected = self.lines, ()
            alert = make_alert(
                targets[0], LineStatus.ALERT if title in (_GROUP, "貝塚線") else LineStatus.UNKNOWN,
                title, text, affected_line_ids=affected,
            )
            for line in targets:
                alerts[line.line_id].append(alert)
        fetched_at = self._now()
        result: list[Line] = []
        for line in self.lines:
            items = tuple(alerts[line.line_id])
            status = LineStatus.UNKNOWN if unknown else LineStatus.ALERT if items else LineStatus.NORMAL
            result.append(snapshot(
                line, status, "\n".join(a.title for a in items) if items else "運行情報欄に掲載なし",
                fetched_at, alerts=items,
            ))
        return tuple(result)

    @property
    def tenjin_omuta(self) -> Line:
        return self._line("line_4e3d73d92dac")

    @property
    def dazaifu(self) -> Line:
        return self._line("line_ab3438d1ea2b")

    @property
    def amagi(self) -> Line:
        return self._line("line_18c851797e51")

    @property
    def kaizuka(self) -> Line:
        return self._line("line_872659be7aa0")
