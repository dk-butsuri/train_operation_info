"""Taiwan High Speed Rail's public, server-rendered service status.

Investigation: both public HTML inspection and archived HTML responses.
https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123
contains current .ts-tag cards and separate collapsed update history. The home
page embeds /ArticleContent/f7f05113-cd27-4dd9-8edc-014f4e920212/index.html;
the full status page supplies incident descriptions, causes, sections and times.
Archived full pages at https://web.archive.org/web/<timestamp>id_/https://www.
thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123:
20240403005339 and 20250227055330 verify caution / 部份列車延誤 (DELAYED);
20241003073858 and 20260711043641 verify caution / 營運班表調整 (ALERT).
The latter label alone does not establish delay or suspension, even when the
body describes time-dependent closures. 20260830041403 and live HTML verify
全線正常營運 (NORMAL), with and without the normal CSS class.
Only current cards determine status; collapsed history never does. Source
update times use Asia/Taipei. Hidden 0001/01/01 and site release dates are not
source update times. Separate station/direction states, full/partial suspension
labels and same-incident recovery captures remain unverified. Unknown markers
or labels remain UNKNOWN with source text; malformed cards fail atomically.
Recovery against normal HTML and malformed/unknown states are synthetic tests.
Fixture extraction, original hashes and terms: tests/fixtures/SOURCES.md.
"""

from datetime import datetime
from typing import Final
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_URL: Final = "https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123"
_ID: Final = ProviderId("thsr")
_LINE_ID: Final = LineId("tw:thsr:main")
_STATES: Final = {
    "全線正常營運": LineStatus.NORMAL,
    "部份列車延誤": LineStatus.DELAYED,
    "營運班表調整": LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Current service-status cards',
        ),
    ),
    provider_id=_ID, name="Taiwan High Speed Rail",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl(
        "https://www.thsrc.com.tw/ArticleContent/b9dcb8ea-02ab-4726-b71d-335904dbd86b",
    ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "THSRC's intellectual-property declaration reserves rights in website "
        "content and requires the rights holder's prior written consent for "
        "quotation or republication. No separate service-status reuse grant was "
        "found on the status page. Public availability does not grant reuse rights."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-01T15:07:17+00:00"),
)


def _required_text(parent: Tag, selector: str) -> str:
    elements = parent.select(selector)
    if len(elements) != 1 or not (text := elements[0].get_text(" ", strip=True)):
        raise ParseError(f"THSR required field is missing or duplicated: {selector}")
    return text


def _parse(html: str, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select(".trafficstatus-container")
    if len(panels) != 1:
        raise ParseError("THSR service-status panel is missing or duplicated")
    panel = panels[0]
    # The update-history records are in .collapse siblings of the current row.
    cards = panel.select(".container > .row > .ts-tag")
    if not cards or len(panel.select(".ts-tag")) != len(cards):
        raise ParseError("THSR current service-status cards changed or are missing")
    statuses: list[LineStatus] = []
    labels: list[str] = []
    alerts: list[ServiceAlert] = []
    timestamps: list[datetime] = []
    for card in cards:
        label = _required_text(card, ".status-ds")
        status = _STATES.get(label, LineStatus.UNKNOWN)
        # CSS and text must agree before reporting a known state.
        markers = set(card.get_attribute_list("class")) - {"ts-tag"}
        expected = {"normal"} if status is LineStatus.NORMAL else {"caution"}
        if markers != expected and not (status is LineStatus.NORMAL and not markers):
            status = LineStatus.UNKNOWN
        details = card.select(".status-detail")
        if len(details) > 1:
            raise ParseError("THSR current incident detail is duplicated")
        title, description = label, label
        if details:
            detail = details[0]
            title = _required_text(detail, ":scope > .thsr-h5")
            raw_time = _required_text(detail, ":scope > span.light-gray")
            prefix = "更新時間 "
            if not raw_time.startswith(prefix):
                raise ParseError("THSR incident update-time label changed")
            timestamps.append(datetime.strptime(raw_time.removeprefix(prefix), "%Y/%m/%d %H:%M").replace(
                tzinfo=ZoneInfo("Asia/Taipei"),
            ))
            body = _required_text(detail, ":scope > p")
            remarks = tuple(item.get_text(" ", strip=True) for item in detail.select(".status-remark > li"))
            if len(remarks) != 2 or not all(remarks) or not (
                remarks[0].startswith("發生原因：") and remarks[0].removeprefix("發生原因：").strip()
                and remarks[1].startswith("影響路段：") and remarks[1].removeprefix("影響路段：").strip()
            ):
                raise ParseError("THSR incident cause or affected section is missing")
            links = tuple(dict.fromkeys(
                urljoin(_URL, href)
                for anchor in detail.select("a[href]")
                if isinstance(href := anchor.get("href"), str) and href.strip() and not href.startswith("#")
            ))
            description = "\n".join((label, title, *remarks, body, *links))
            if status is LineStatus.NORMAL:
                # A green card with an incident is contradictory, not an all-clear.
                status = LineStatus.UNKNOWN
        elif status in (LineStatus.DELAYED, LineStatus.ALERT):
            raise ParseError("THSR current incident detail is missing")
        if status is not LineStatus.NORMAL:
            alerts.append(make_alert(line, status, title, description, language="zh-Hant"))
        statuses.append(status)
        labels.append(label)
    return (snapshot(
        line, combined_status(tuple(statuses)), "\n".join(labels), fetched_at,
        updated_at=max(timestamps) if timestamps else None, alerts=tuple(alerts),
    ),)


class ThsrProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__((LINE_CATALOG[_LINE_ID].create_line(_ID, _URL),), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.main, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")
