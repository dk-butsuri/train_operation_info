"""Fukuoka City Transportation Bureau's official subway service notices.

Investigation: public HTML/JavaScript and Wayback archives, 2026-11-04 UTC.
https://subway.city.fukuoka.lg.jp/status/ renders the current notice directly
in #status .box02 dl > dt .statusNews. Archives 20230711012832,
20241224075857, 20250501031503 and 20260527005254 contain the same exact
normal paragraph as live HTML. Archive 20240829161647id_ of that URL
contains a typhoon suspension PLAN in the same panel, with the SAME st02
icon as normal service. The icon is therefore not a disruption status code.
Only the complete normal paragraph maps to NORMAL; other notices map to
ALERT with original text/links and affected_line_ids=(). The panel has no
structured affected routes; all three lines carry the shared announcement.
Neither prose nor icon determines delay/suspension or timing=ACTIVE.

The right-aligned dt child contains an explicit full-year 更新 timestamp
in the notice archive (Japan local time); empty means updated_at=None.
The separate .data 現在 timestamp advances at page rendering, not publication,
and is never used as updated_at. timing=UNKNOWN; active_from/until=None.
The header's running.json is only a summary. /js/suspension_header.js reads
separate suspension.json for planned changes; neither is fetched. Plans
published inside the current panel are retained without inferred timing.
Separate planned changes, history, certificates, positions and linked pages
are excluded; raw HTML recordings can still contain their links/header.
Real normal/plan captures verify parsing. Other impacts, narrative variants,
corruption and notice clearing sequences are explicitly synthetic tests.
Evidence/hashes: tests/fixtures/FUKUOKA_SUBWAY.md, fukuoka_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

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

_URL: Final = "https://subway.city.fukuoka.lg.jp/status/"
_ID: Final = ProviderId("fukuoka_subway")
_NORMAL: Final = "通常運行しています。"
_ROUTES: Final = tuple(LineId("jp:operator_afa22347b935:" + key) for key in (
    "line_10f28d664b10", "line_11ed84bd24c5", "line_927daf7c388e",
))
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Fukuoka City Subway official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Current subway notice panel; separate planned changes and linked pages excluded",
    ),),
    terms_url=HttpUrl("https://subway.city.fukuoka.lg.jp/utility/"),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note=(
        "The official site terms prohibit information use beyond the permitted "
        "scope of private use. No public or commercial reuse grant was found. "
        "Only the current subway panel is parsed; through-running JR lines and "
        "the separate planned-suspension feed are outside scope."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:11:37.038925+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Fukuoka Subway element missing or duplicated: {selector}")
    return matches[0]


def _notice(payload: bytes) -> tuple[str, datetime | None, bool]:
    soup = BeautifulSoup(payload.decode("utf-8-sig"), "html.parser")
    section = _one(soup, "section#status")
    if _one(section, "h2.ttl_h2").get_text(strip=True) != "運行情報":
        raise ParseError("Unexpected Fukuoka Subway page heading")
    _one(soup, "footer")  # Do not accept a truncated success response as normal.
    panel = _one(section, ".box02")
    dt = _one(panel, "dl > dt")
    _one(panel, "dl > dd")
    icon = _one(dt, "span.status")
    body = _one(dt, "div.statusNews")
    updated = _one(dt, 'div[align="right"]')
    children = [n for n in dt.children if not isinstance(n, Comment) and str(n).strip()]
    if len(children) != 3 or any(a is not b for a, b in zip(children, (icon, body, updated))):
        raise ParseError("Unexpected Fukuoka Subway notice structure")
    if dt.select("script, style, iframe, template"):
        raise ParseError("Unexpected executable Fukuoka Subway notice content")
    for image in body.select("img"):
        image.replace_with(NavigableString(str(image.get("alt", ""))))
    text = body.get_text("\n", strip=True)
    if not text:
        raise ParseError("Empty Fukuoka Subway notice")
    links: list[str] = []
    for link in body.select("a"):
        href = link.get("href")
        if not isinstance(href, str) or not href.strip():
            raise ParseError("Fukuoka Subway notice link missing destination")
        target = urljoin(_URL, href)
        HttpUrl(target)
        links.append(target)
    updated_at = None
    stamp = updated.get_text(" ", strip=True)
    if stamp:
        # This is the dedicated publication field, never the page's 現在 clock.
        match = re.fullmatch(r"(\d{4})年(\d{2})月(\d{2})日\s+(\d{2})時(\d{2})分\s+更新", stamp)
        if match is None:
            raise ParseError("Unexpected Fukuoka Subway update timestamp")
        year, month, day, hour, minute = (int(v) for v in match.groups())
        updated_at = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tokyo"))
    return "\n".join((text, *dict.fromkeys(links))), updated_at, text == _NORMAL and not links


class FukuokaSubwayProvider(SnapshotProvider):
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
        text, updated_at, normal = _notice(response.content)
        status = LineStatus.NORMAL if normal else LineStatus.ALERT
        alerts = () if normal else (make_alert(
            self.kuko, status, "福岡市地下鉄 運行情報", text, affected_line_ids=(),
        ),)
        fetched_at = self._now()
        return tuple(snapshot(
            line, status, text, fetched_at, updated_at=updated_at, alerts=alerts,
        ) for line in self.lines)

    @property
    def kuko(self) -> Line:
        return self._line("line_10f28d664b10")

    @property
    def hakozaki(self) -> Line:
        return self._line("line_11ed84bd24c5")

    @property
    def nanakuma(self) -> Line:
        return self._line("line_927daf7c388e")
