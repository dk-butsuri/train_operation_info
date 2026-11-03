"""Keio official service alerts.

Investigation: both public-source inspection and archive. The operation page
https://www.keio.co.jp/unkou/unkou_pc.html server-renders the current message
inside ".unko_txt .status", matching what it polls at
https://www.keio.co.jp/_system/_unkou/unkouInformation.xml. This is confirmed
by /cmn_js/unkou_time.js (Shift_JIS), which AJAX-polls that XML on load and on
the page's "更新" button, reading <emergency>/<unkouInformation>/<time> with
jQuery; it only drives the displayed update clock and a loading indicator, not
an alternate data source. /cmn_js/unkou_cookie_manager.js only stores the
auto-refresh interval cookie and carries no status data.

A live capture on 2026-11-03 and CDX captures from 2011-05-31 through
2024-05-30 (most recently 20240530150807, which also shows the XML switching
from Shift_JIS to UTF-8 around 2024, matching the current live encoding) are
all "emergency=false" with the fixed sentence
"京王線・井の頭線は平常通り運転しています。". The only abnormal capture found,
20190909043234 (UTC), has "emergency=true" with the free-text body
"井の頭線　運転を見合せています" (Inokashira Line suspended), naming only one
of the two groups the normal sentence names together. With a single abnormal
sample and no documented, stable template separating an affected group from
the rest of the sentence, this body text does not establish a verified
per-line mapping. "emergency=false" together with the exact fixed sentence is
therefore the only basis for NORMAL, applied to every one of the seven
canonical lines the source reports as one group; any other "emergency" value
(including "true"), or "false" with any other body, keeps every line UNKNOWN with a single shared alert carrying the raw body and
affected_line_ids=(), the same whole-network/unidentified-scope treatment as
Hanshin and Osaka Monorail. "imgTime"/"lang_time" duplicate "time" in other
formats and are not used. No per-line breakdown, delay-only code, or incident
validity period is published here, so updated_at uses <time> (Asia/Tokyo) and
timing stays UNKNOWN. Evidence, raw captures and hashes: tests/fixtures/KEIO.md.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.keio.co.jp/_system/_unkou/unkouInformation.xml"
_PAGE_URL: Final = "https://www.keio.co.jp/unkou/unkou_pc.html"
_ID: Final = ProviderId("keio")
# Reuse the canonical IDs already shared by the Yahoo provider.
_ROUTES: Final = (
    ("main", "京王線", LineId("jp:keio:line_0cb7d2efef5d")),
    ("shinsen", "京王新線", LineId("jp:keio:line_3c2563f11b2a")),
    ("sagamihara", "京王相模原線", LineId("jp:keio:line_25cd0e31969a")),
    ("takao", "京王高尾線", LineId("jp:keio:line_5e6de121e906")),
    ("keibajo", "京王競馬場線", LineId("jp:keio:line_d155e8d8cfa8")),
    ("doubutsuen", "京王動物園線", LineId("jp:keio:line_da0cc13de9db")),
    ("inokashira", "京王井の頭線", LineId("jp:keio:line_1690db7527c8")),
)

_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Keio official", source_page_url=HttpUrl(_PAGE_URL),
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.XML,
            description="Network-wide emergency flag, free-text message and update time",
        ),
    ),
    terms_url=HttpUrl("https://www.keio.co.jp/contact/site/"),
    additional_terms_urls=(HttpUrl(_PAGE_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site terms' copyright section declines reproduction, repurposing, "
        "reprinting, electronic processing, transmission, distribution and "
        "secondary use of all site content without exception; it states no "
        "private-use carve-out. The operation page separately discloses a "
        "roughly 15-minute delay threshold and disclaims the accuracy and "
        "timeliness of the published information."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-03T04:30:00+00:00"),
)

_NORMAL_TEXT: Final = "京王線・井の頭線は平常通り運転しています。"
_TIME_RE: Final = re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}")


def _parse_time(text: str) -> datetime:
    if _TIME_RE.fullmatch(text) is None:
        raise ParseError("Malformed Keio update time")
    return datetime.strptime(text, "%Y/%m/%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Tokyo"))


def _parse(xml: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    root = ET.fromstring(xml)
    if root.tag != "unkou":
        raise ParseError("Invalid Keio unkou root")
    emergency_text = root.findtext("emergency")
    message = root.findtext("unkouInformation")
    time_text = root.findtext("time")
    if emergency_text is None or message is None or not message.strip() or time_text is None:
        raise ParseError("Incomplete Keio official status")
    updated_at = _parse_time(time_text)
    body = message.strip()
    # Only the structured false value is evidence of network-wide NORMAL.
    # Any other value (true, or an unrecognized future value) keeps every
    # line UNKNOWN: a single abnormal sample names only one of the two
    # groups the normal sentence names together, so the free text does not
    # establish a verified per-line scope.
    # The false flag alone is not enough: an unverified body under it must not
    # be discarded, so it is NORMAL only with the verified fixed sentence.
    normal = emergency_text == "false" and body == _NORMAL_TEXT
    status = LineStatus.NORMAL if normal else LineStatus.UNKNOWN
    alerts = () if normal else (make_alert(
        lines[0], LineStatus.UNKNOWN, "京王電鉄: 運行情報（対象路線未特定）", body,
        affected_line_ids=(),
    ),)
    source_status = f"emergency={emergency_text}\n{body}"
    return tuple(
        snapshot(line, status, source_status, fetched_at, updated_at=updated_at, alerts=alerts)
        for line in lines
    )


class KeioProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE_URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _PAGE_URL)
            for _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("line_0cb7d2efef5d")

    @property
    def shinsen(self) -> Line:
        return self._line("line_3c2563f11b2a")

    @property
    def sagamihara(self) -> Line:
        return self._line("line_25cd0e31969a")

    @property
    def takao(self) -> Line:
        return self._line("line_5e6de121e906")

    @property
    def keibajo(self) -> Line:
        return self._line("line_d155e8d8cfa8")

    @property
    def doubutsuen(self) -> Line:
        return self._line("line_da0cc13de9db")

    @property
    def inokashira(self) -> Line:
        return self._line("line_1690db7527c8")
