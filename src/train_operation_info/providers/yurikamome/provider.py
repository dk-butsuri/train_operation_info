"""Yurikamome's official service-status feed.

Investigation: public JavaScript inspection and archived HTML cross-checks.
https://www.yurikamome.co.jp/ride-guidance/operation.html loads
https://www.yurikamome.co.jp/assets/js/common.js?date=190718, which reads
https://cms-2.yurikamome.co.jp/api/operation/ and renders .info_title,
.info_update and .info_text. Its switch explicitly names the abnormal labels;
their meanings determine the mappings below, not keywords in incident prose.
Restart and other notices remain ALERT, since they do not establish normality
or delay. Unknown labels retain their text as UNKNOWN.

All 10 distinct successful HTML captures in the endpoint's Wayback CDX index
(2019-2021) were inspected; none contained an incident. In particular,
https://web.archive.org/web/20191003184453id_/https://cms-2.yurikamome.co.jp/api/operation/
has a normal title but only an out-of-hours notice. NORMAL requires both the
known title and the explicit normal message; out-of-hours notices are UNKNOWN.
The live response verifies normal operation and the full Japanese date format.
Displayed distribution times use Asia/Tokyo, never the reader or fetch clock.
Abnormal responses, recovery and malformed/unknown cases are synthetic tests
based on the published switch; actual abnormal and same-incident recovery
responses remain unverified. No separate station/direction status, structured
cause/section fields or delay certificates are fetched. Evidence and hashes:
tests/fixtures/YURIKAMOME.md and yurikamome_manifest.json.
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

_URL: Final = "https://www.yurikamome.co.jp/ride-guidance/operation.html"
_FEED_URL: Final = "https://cms-2.yurikamome.co.jp/api/operation/"
_ID: Final = ProviderId("yurikamome")
# Reuse the canonical route already shared with Yahoo (source route 160/0).
_LINE_ID: Final = LineId("jp:operator_c0a210bf19c5:line_cbfd3a81aaf1")
_NORMAL_TEXT: Final = "現在、平常通り運転しています。"
_STATES: Final = {
    "平常運転": LineStatus.NORMAL,
    "遅延": LineStatus.DELAYED,
    "運転見合わせ": LineStatus.SUSPENDED,
    "運転再開見込": LineStatus.SUSPENDED,
    "運休": LineStatus.SUSPENDED,
    "一部運休": LineStatus.PARTIAL_SUSPENSION,
    "折返し運転": LineStatus.PARTIAL_SUSPENSION,
    "一部運転再開": LineStatus.PARTIAL_SUSPENSION,
    "運転再開": LineStatus.ALERT,
    "直通運転再開": LineStatus.ALERT,
    "バス代行": LineStatus.ALERT,
    "経路変更": LineStatus.ALERT,
    "リフレッシュ工事": LineStatus.ALERT,
    "お知らせ": LineStatus.ALERT,
    "直通運転中止": LineStatus.ALERT,
    "お詫び": LineStatus.ALERT,
    "自由文": LineStatus.ALERT,
    "振替輸送": LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_FEED_URL, method="GET", format=DataFormat.HTML,
            description='Status title, distribution time and notice',
        ),
    ),
    provider_id=_ID, name="Yurikamome official",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.yurikamome.co.jp/utility/policy.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note=(
        "The site policy reserves copyright and requires prior permission for "
        "reuse except private copying, quotation and other uses permitted by law. "
        "No commercial reuse grant was found. The operation page publishes delays "
        "of roughly 15 minutes or more, including anticipated delays, and warns "
        "that its information may differ from actual service."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T02:28:35+00:00"),
)


def _required_text(parent: Tag, selector: str) -> str:
    fields = parent.select(selector)
    if len(fields) != 1:
        raise ParseError(f"Yurikamome field is missing or duplicated: {selector}")
    text = fields[0].get_text("\n", strip=True)
    if not text or text == "-":
        raise ParseError(f"Yurikamome field is empty: {selector}")
    return text


def _parse(html: str, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select("aside.info")
    if len(panels) != 1:
        raise ParseError("Yurikamome service-status panel is missing or duplicated")
    panel = panels[0]
    label = _required_text(panel, ".info_title")
    raw_time = _required_text(panel, ".info_update")
    body = _required_text(panel, ".info_text").removeprefix("[運行状況]").strip()
    if not body or body == "-":
        raise ParseError("Yurikamome service-status message is empty")
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})時(\d{1,2})分\s+配信", raw_time)
    if match is None:
        raise ParseError("Yurikamome distribution time format changed")
    year, month, day, hour, minute = (int(value) for value in match.groups())
    updated_at = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tokyo"))
    status = _STATES.get(label, LineStatus.UNKNOWN)
    if status is LineStatus.NORMAL and body != _NORMAL_TEXT:
        status = LineStatus.UNKNOWN
    alerts = () if status is LineStatus.NORMAL else (make_alert(line, status, label, body),)
    return (snapshot(line, status, label, fetched_at, updated_at=updated_at, alerts=alerts),)


class YurikamomeProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE_ID].create_line(_ID, _URL),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED_URL)
        response.raise_for_status()
        return _parse(response.text, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
