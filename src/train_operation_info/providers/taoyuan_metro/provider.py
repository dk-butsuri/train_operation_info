"""Taoyuan Metro's official Airport MRT operating-status display.

Investigation: public HTML/JavaScript inspection and archived official HTML.
https://www.tymetro.com.tw/tymetro-new/tw/ renders two .banner .operation
panels (mobile and desktop), each headed 最新營運狀態. The status span is
server-rendered; /tymetro-new/js/custom.js updates #timereload as the current
clock, not an incident update time. template.js and web.min.js expose no
additional status mapping. No API key or login is used.

Official homepage captures at https://web.archive.org/web/<timestamp>id_/
https://www.tymetro.com.tw/tymetro-new/tw/ verify:
20240403012130: red + 全線停駛 -> SUSPENDED;
20240408100245 and 20241001015424: green + 正常營運 -> NORMAL;
20260711043649: yellow + 減速營運 -> ALERT.
Live HTML on 2026-11-04 confirms the normal pair and the same two panels.
Reduced speed does not establish actual delay or fewer trains, so its effect
is OTHER. Labels and CSS classes must agree; unknown pairs keep UNKNOWN and
the original label/marker. Missing/empty/duplicate or conflicting responsive
panels abort the refresh. Icons are decorative and do not classify status.

Coverage is the single Airport MRT line, without splitting local and express
services or inferring affected sections. Separate news, linked articles, PDFs,
train positions, timetables and planned works are excluded. Raw HTTP captures
still contain those excluded page sections. NORMAL refers only to this panel.
No source update time or validity interval is published in it: updated_at and
active_from/active_until remain None. Applicability mapping is unverified, so
timing stays UNKNOWN; prose and the page clock never supply it.

The later normal archive verifies normal after the suspension, but not the
exact reopening time or an explicit same-incident recovery statement. Unknown,
contradictory, malformed and transport-failure cases are synthetic. Delay and
partial-suspension labels remain unverified and are not classified. Sources,
terms, retrieval times and hashes: tests/fixtures/TAOYUAN_METRO.md and
taoyuan_metro_manifest.json. Third-party response bodies stay local.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, LINE_CATALOG, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.tymetro.com.tw/tymetro-new/tw/"
_ID: Final = ProviderId("taoyuan_metro")
_LINE_ID: Final = LineId("tw:tymetro:airport")
_STATES: Final = {
    ("green", "正常營運"): LineStatus.NORMAL,
    ("red", "全線停駛"): LineStatus.SUSPENDED,
    ("yellow", "減速營運"): LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Taoyuan Metro (Airport MRT)",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Airport MRT current operating-status panels (desktop/mobile)",
    ),),
    terms_url=HttpUrl("https://www.tymetro.com.tw/tymetro-new/tw/_pages/note/intellect.html"),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The official intellectual-property declaration requires consent or "
        "authorisation to reuse protected website content outside fair use. "
        "It reserves personal/family non-profit copying and reasonable quotation, "
        "and requests source attribution for the stated fair-use cases. No "
        "separate service-status reuse licence was found."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:40:35.795143+00:00"),
)


def _parse(html: str, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select(".banner .operation")
    if len(panels) != 2:
        raise ParseError("Taoyuan Metro operating panels are missing or duplicated")
    values: list[tuple[tuple[str, ...], str]] = []
    for panel in panels:
        paragraphs = panel.select(":scope > p")
        if len(paragraphs) != 1:
            raise ParseError("Taoyuan Metro operating panel structure changed")
        paragraph = paragraphs[0]
        spans = paragraph.select(":scope > span")
        if len(spans) != 1:
            raise ParseError("Taoyuan Metro operating status is missing or duplicated")
        label = spans[0].get_text(" ", strip=True)
        markers = tuple(sorted(spans[0].get_attribute_list("class")))
        if not label or not markers or paragraph.get_text("", strip=True) != "最新營運狀態" + label:
            raise ParseError("Taoyuan Metro operating status or heading is empty or changed")
        values.append((markers, label))
    if values[0] != values[1]:
        raise ParseError("Taoyuan Metro desktop and mobile operating statuses disagree")
    markers, label = values[0]
    status = _STATES.get((" ".join(markers), label), LineStatus.UNKNOWN)
    raw = label if status is not LineStatus.UNKNOWN else f"{label} [{' '.join(markers)}]"
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, "桃園捷運營運狀態", raw, language="zh-Hant"),
    )
    return (snapshot(line, status, raw, fetched_at, alerts=alerts),)


class TaoyuanMetroProvider(SnapshotProvider):
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
        return _parse(response.content.decode("utf-8"), self.airport, self._now())

    @property
    def airport(self) -> Line:
        return self.lines[0]
