"""Yui Rail (Okinawa Urban Monorail) top-page operation notice.

Investigation: public JavaScript inspection plus archived JSON responses.
https://www.yui-rail.co.jp/ shows the 運行情報 marquee in
``p.js-opt-info-text``. https://www.yui-rail.co.jp/common/js/layout.min.js
(ver=1786500098) fetches
https://www.yui-rail.co.jp/common/json/data/operation_info.json?t=<epoch ms>
with ``cache: "no-store"`` and writes the ``text`` of the current language into
that element, wrapping it in a link only when ``link`` is non-empty. The payload
has one ``{text, link}`` entry per language (en, tc, sc, kr, jp). It carries no
status code, no per-line or per-section field, and no timestamp, so the notice
is the only machine-readable signal.

The Wayback CDX index lists 12 captures of this endpoint between 2026-03-09 and
2026-09-05 (6 distinct bodies). Three distinct non-normal texts were observed:
a 2026-06-01 all-day suspension for Typhoon No. 6, a 2026-08-07 all-day
suspension for Typhoon No. 13, and a 2026-08-25 text that reports normal
operation while warning about the next day. The latter shows that non-normal
text does not always mean an incident, and none of the samples exposes a
structured impact. Prose therefore never sets DELAYED or SUSPENDED: only the
exact normal sentences below yield NORMAL, everything else is ALERT with the
original text retained as required by the common policy. No dedicated status
field establishes a current fault, so every alert keeps timing=UNKNOWN and no
active_from/active_until is derived from the text.

Normal texts verified live and in captures: "現在、平常通り運行しております。"
(live, 2026-03-09, 2026-08-01) and the same sentence without the trailing
"。" (2026-03-26). Any other sentence, including a rewritten normal message,
stays ALERT. ``updated_at`` is None because the payload has no distribution
time; the fetch clock is not substituted. ``link`` targets and delay
certificates are not fetched, and station/direction detail is unavailable.
The two archived typhoon notices are the only real incident bodies; recovery
after an incident, malformed, contradictory and unknown cases are synthetic
tests. Evidence and hashes: tests/fixtures/YUIRAIL.md and
yuirail_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.yui-rail.co.jp/"
_FEED_URL: Final = "https://www.yui-rail.co.jp/common/json/data/operation_info.json"
_ID: Final = ProviderId("yuirail")
# Reuse the canonical route already shared with Yahoo (Okinawa Urban Monorail).
_LINE_ID: Final = LineId("jp:operator_95b01abb482d:line_b8a42de95ac6")
_ALERT_TITLE: Final = "運行情報"
# Exact Japanese sentences that the source uses for normal operation.
_NORMAL_TEXTS: Final = frozenset({
    "現在、平常通り運行しております。",
    "現在、平常通り運行しております",
})
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_FEED_URL, method="GET", format=DataFormat.JSON,
            description="Per-language operation notice shown in the top-page marquee",
        ),
    ),
    provider_id=_ID, name="Yui Rail official",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.yui-rail.co.jp/policy/"),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site's サイトご利用案内 reserves copyright in all posted information "
        "and states that unauthorised reproduction or republication in any medium "
        "is refused. No separate reuse grant for the operation notice was found. "
        "The notice is a single sentence that may describe the current day or the "
        "next day's plans, and the company may change or stop publishing it "
        "without prior notice."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-02T15:39:27+00:00"),
)


class _Notice(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    text: str
    link: str


class _OperationInfo(BaseModel):
    # Only the Japanese text is consumed; other languages are ignored.
    model_config = ConfigDict(strict=True, extra="ignore")
    jp: _Notice


def _parse(payload: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    data = _OperationInfo.model_validate_json(payload)
    text = data.jp.text.strip()
    if not text:
        raise ParseError("Yui Rail operation notice is empty")
    status = LineStatus.NORMAL if text in _NORMAL_TEXTS else LineStatus.ALERT
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, _ALERT_TITLE, text),
    )
    return (snapshot(line, status, text, fetched_at, alerts=alerts),)


class YuiRailProvider(SnapshotProvider):
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
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
