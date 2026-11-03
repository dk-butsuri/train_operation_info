"""Kyoto City Transportation Bureau's official emergency notices.

Investigation: public HTML/JavaScript and Wayback archives, 2026-11-03 UTC.
https://www.city.kyoto.lg.jp/kotsu/category/166-0-0-0-0-0-0-0-0-0.html
documents that subway disruptions appear in the homepage emergency panel.
https://www.city.kyoto.lg.jp/kotsu/ embeds that panel between dedicated
緊急情報 comments. /main/css/img/onload_ku_top.js?20260729 has no status feed.
Wayback 20230815040858id_/https://www.city.kyoto.lg.jp/kotsu/ contains
through-service, bus and disaster notices together; 20230816075536id_ has
the explicit no-emergency paragraph. Live HTML and 20240827141354,
20250802110421 and 20251031085732 archives have an empty marked region.

NORMAL means no published emergency notice in this scope, not proof of all
services running normally. Nonempty notices yield UNKNOWN on both lines,
with affected_line_ids=(): neither route nor effect is structurally specified.
No narrative matching, date inference or per-route suspension classification.
timing=UNKNOWN; updated_at/active_from/active_until=None. Homepage summaries
and their link destinations are retained; linked article bodies, separate news,
planned service changes, certificates, timetables and bus feeds are not fetched.
Separate news may be in the recorded HTML but is not parsed as current status.
Missing/duplicate/reordered markers or panel structure raise ParseError.
Tests use real normal/notice/cleared archives plus explicit synthetic corruption
and narrative cases. Per-route disruption states remain unverified.
Evidence and hashes: tests/fixtures/KYOTO_SUBWAY.md and kyoto_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.city.kyoto.lg.jp/kotsu/"
_ID: Final = ProviderId("kyoto_subway")
_ROUTES: Final = (
    LineId("jp:operator_9e7399db41b2:line_a4f8893160fb"),
    LineId("jp:operator_9e7399db41b2:line_bc4a5426cc32"),
)
_START: Final = "▼▼緊急情報▼▼"
_END: Final = "▲▲緊急情報▲▲"
_EMPTY: Final = "緊急情報はありません。緊急情報がある場合、この欄に掲載されます。"
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Kyoto City Subway official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Homepage emergency panel; linked articles and separate news are not fetched",
    ),),
    terms_url=HttpUrl("https://www.city.kyoto.lg.jp/main/site_policy/0000000005.html"),
    additional_terms_urls=(HttpUrl(
        "https://www.city.kyoto.lg.jp/kotsu/category/166-0-0-0-0-0-0-0-0-0.html",
    ),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "Kyoto City's copyright policy prohibits unauthorized copying or reuse except "
        "private copying, quotation and other uses permitted by copyright law. "
        "No separate reuse grant for service notices was found."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-03T15:59:20+00:00"),
)


def _one(parent: Tag | BeautifulSoup, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Kyoto Subway element missing or duplicated: {selector}")
    return matches[0]


def _notice(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    body = _one(soup, "body.ku_top")
    main = _one(body, "#main")
    lower = _one(main, "#main_lower")
    _one(body, "#foot")  # A truncated successful response must not imply normal service.
    markers = [
        node for node in soup.find_all(string=True)
        if isinstance(node, Comment) and str(node).strip() in (_START, _END)
    ]
    if (len(markers) != 2 or str(markers[0]).strip() != _START
            or str(markers[1]).strip() != _END
            or any(node.parent is not main for node in markers) or lower.parent is not main):
        raise ParseError("Kyoto Subway emergency markers missing, duplicated or misplaced")
    children = list(main.children)
    start, end, tail = (children.index(node) for node in (*markers, lower))
    if not start < end < tail:
        raise ParseError("Kyoto Subway emergency markers are out of order")
    region = BeautifulSoup("".join(str(node) for node in children[start + 1:end]), "html.parser")
    content = [node for node in region.contents if not isinstance(node, Comment) and str(node).strip()]
    if not content:
        if soup.select("#imp"):
            raise ParseError("Kyoto Subway emergency panel outside its marked region")
        return None
    panel = _one(region, "div#imp")
    if len(content) != 1 or content[0] is not panel or len(soup.select("#imp")) != 1:
        raise ParseError("Unexpected Kyoto Subway emergency region content")
    heading = _one(panel, "h2 img")
    if heading.get("alt") != "緊急情報":
        raise ParseError("Unexpected Kyoto Subway emergency heading")
    notice = _one(panel, ".imp_lower")
    if notice.select("script, style, iframe, template"):
        raise ParseError("Unexpected executable Kyoto Subway emergency content")
    for extra in notice.select(".img_lst"):
        extra.decompose()  # Standing disaster-portal link, present in the cleared archive too.
    for image in notice.select("img"):
        image.replace_with(NavigableString(str(image.get("alt", ""))))
    text = notice.get_text("\n", strip=True)
    links: list[str] = []
    for link in notice.select("a"):
        href = link.get("href")
        if not isinstance(href, str) or not href.strip():
            raise ParseError("Kyoto Subway emergency link is missing its destination")
        target = urljoin(_URL, href)
        HttpUrl(target)
        links.append(target)
    if text == _EMPTY and not links and not region.select(".imp_kinkyu, .imp_kinkyu_lower"):
        return None
    if not text:
        raise ParseError("Kyoto Subway emergency panel is empty")
    return "\n".join((text, *dict.fromkeys(links)))


class KyotoSubwayProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL) for identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        description = _notice(response.content.decode("utf-8-sig"))
        status = LineStatus.NORMAL if description is None else LineStatus.UNKNOWN
        alerts = () if description is None else (make_alert(
            self.lines[0], status, "京都市交通局 緊急情報", description, affected_line_ids=(),
        ),)
        fetched_at = self._now()
        return tuple(snapshot(
            line, status, "緊急情報欄に掲載なし" if description is None else "緊急情報欄に掲載あり",
            fetched_at, alerts=alerts,
        ) for line in self.lines)

    @property
    def karasuma(self) -> Line:
        return self._line("line_a4f8893160fb")

    @property
    def tozai(self) -> Line:
        return self._line("line_bc4a5426cc32")
