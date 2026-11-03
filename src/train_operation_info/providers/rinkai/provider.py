"""Rinkai Line's official service notice for Osaki--Shin-kiba.

Investigation: public HTML/script inspection and archived official HTML.
https://service.twr.co.jp/rinkai/public/information?lang=ja renders #serviceInfo
server-side. The homepage's /service_info/top.js redirects to
/rinkai/public/top?lang=ja and writes an anchor containing the notice; it has
no status-code mapping. /service_info/information.html redirects to the source
URL above. CSS only styles the page. No separate structured status API found.

Wayback captures at the following original URLs verify the message structure:
https://web.archive.org/web/20180122093824id_/http://service.twr.co.jp/service_info/information.html
and 20180904125255 at the same URL: snow/obstruction, JR through-service
cancellation, turnback and delays, with p.date explicitly labelled 更新.
https://web.archive.org/web/20191012171221id_/https://service.twr.co.jp/service_info/information.html
contains a typhoon suspension and conditional next-day reopening.
https://web.archive.org/web/20220825002322id_/https://service.twr.co.jp/rinkai/public/information?lang=ja
contains delays, followed by normal at 20220825005348 (same original URL).
20220926105254 at that URL contains turnback/through-service cancellation.

There is no distinct status code or label: only the complete verified normal
message maps to NORMAL; other notices map to ALERT with their original prose.
We do not infer DELAYED/SUSPENDED/PARTIAL_SUSPENSION from narrative keywords,
or mark the entire Rinkai line suspended when JR through-service is cancelled.
Normal text mixed with additional information is UNKNOWN and retained.
Only p.date's explicit full Japanese update date maps to updated_at, Asia/Tokyo.
The #nowTime value advances between live requests even with unchanged normal
text: it is the page clock, not an update time. Normal pages have no p.date.

No dedicated duration or applicability fields exist. The archived typhoon
notice mixes current and conditional future service and uses yearless dates
in its prose; timing remains UNKNOWN, active_from/active_until unset.
Long-term/standalone partial closure notices and current abnormal HTML remain
unverified. Malformed/contradictory tests are synthetic. Normal after the delay
is a real chronological capture, though its text does not name the prior event.

Only #serviceInfo is fetched, not separate homepage news, linked articles,
positions, delay certificates or official X. NORMAL refers to this panel's
publication threshold (30+ minutes, anticipated delays and through-service
cancellation), not the absence of smaller delays or separate planned changes.
Evidence, UTC capture/retrieval times, hashes and terms review are documented in
tests/fixtures/RINKAI.md and rinkai_manifest.json.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://service.twr.co.jp/rinkai/public/information?lang=ja"
_ID: Final = ProviderId("rinkai")
# Reuse the route and operator already registered for Yahoo; snapshots stay separate.
_LINE_ID: Final = LineId("jp:operator_a76aef032695:line_68e848012d4b")
_NORMAL: Final = "平常通り運転しています。"
_TITLE: Final = "りんかい線 運行情報"
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Japanese service notice',
        ),
    ),
    provider_id=_ID, name="Rinkai official", source_page_url=HttpUrl(_URL),
    terms_url=None,
    additional_terms_urls=(HttpUrl(_URL), HttpUrl("https://www.twr.co.jp/about/tabid/197/Default.aspx")),
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note=(
        "No general website reuse terms or service-HTML reuse licence was found "
        "in the reviewed homepage/navigation and service page. The linked social "
        "media terms require written consent for reuse of official-account content; "
        "their stated scope is official accounts and associated services, so they "
        "are not treated as a licence for this separate HTML feed. No commercial "
        "reuse grant was found. The service page warns that information may differ "
        "from actual operation and covers 30-minute/anticipated delays, JR through-"
        "service cancellation and suspended operation. Separate news is not fetched."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-02T05:52:15.263408+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Rinkai element missing or duplicated: {selector}")
    return matches[0]


def _parse(html: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    # Parse the charset declared in the original HTML, independent of HTTP defaults.
    soup = BeautifulSoup(html, "html.parser")
    header = _one(soup, ".contBody h1 img")
    if header.get("alt") != _TITLE:
        raise ParseError("Rinkai page identity changed")
    panel = _one(soup, "#serviceInfo")
    if panel not in _one(soup, ".contBodyPage").descendants:
        raise ParseError("Rinkai service panel is outside the page body")
    for hidden in panel.select("script, style, template, noscript"):
        hidden.decompose()
    dates = panel.select(".date")
    if len(dates) > 1:
        raise ParseError("Rinkai update date is duplicated")
    updated_at = None
    if dates:
        date = dates[0]
        raw_date = date.get_text(" ", strip=True)
        match = re.fullmatch(
            r"（(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2})時(\d{1,2})分更新）", raw_date,
        )
        if date.name != "p" or match is None:
            raise ParseError("Rinkai explicit update date format changed")
        year, month, day, hour, minute = (int(value) for value in match.groups())
        updated_at = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tokyo"))
        date.decompose()
    body = panel.get_text("\n", strip=True)
    if not body or body == "-":
        raise ParseError("Rinkai service notice is empty")
    compact = "".join(body.split())
    if compact == _NORMAL:
        status = LineStatus.NORMAL
    elif _NORMAL in compact:
        status = LineStatus.UNKNOWN
    else:
        status = LineStatus.ALERT
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, _TITLE, body),
    )
    return (snapshot(line, status, body, fetched_at, updated_at=updated_at, alerts=alerts),)


class RinkaiProvider(SnapshotProvider):
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
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
