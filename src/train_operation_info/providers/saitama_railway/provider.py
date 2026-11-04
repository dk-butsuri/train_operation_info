"""Saitama Railway's official current service messages, Akabane-iwabuchi--Urawa-misono.

Investigation: public HTML/JavaScript inspection, not abnormal archive evidence.
https://www.s-rail.co.jp/ticket/train/ fetches /service_status/status.json and
renders only messages with latest=true in createTrainNote; createTable separately
renders the history. The homepage https://www.s-rail.co.jp/ uses the same feed,
but only its first entry. Follow the dedicated service page's latest flags.

createTrainNote gives type=stdtxt the normal (o) icon. For type=message it uses
langs.ja.status and the explicit STATUS_TYPES table. Map the dedicated labels
平常運転, 遅延, 運転見合わせ/運休 and 一部運休 directly; other documented labels
are ALERT, without interpreting prose or the shared warning/suspension icons.
Unknown labels/types (including overtime) remain UNKNOWN with their text.
Only stdtxt has been captured live. Abnormal payloads, multiple latest messages,
overtime, missing/latest=false flags and recovery tests are synthetic. The exact
JSON URL's Wayback CDX query returned no captures; abnormal JSON is unverified.

The history table labels msg.time as 発信日時 and formats YYYYMMDDHHmm[ss].
Use its full 14-digit timestamp in Japan local time for the current notice's
publication time (updated_at); ignore the envelope's time/created (generation).
latest means currently displayed, not necessarily currently effective: timing
stays UNKNOWN, with no inferred active period or future/duration classification.
There is no separate long-term field in the inspected current-message renderer;
keep all latest notices. Exclude history, separate news, delay certificates,
replacement-transport pages and through-running operators' own statuses.
Empty/history-only feeds are UNKNOWN, never evidence of normal operation.

The official site policy requires consent for printing, quoting or repurposing
site information; no reuse licence is inferred from anonymous HTTP access.
Evidence, hashes and unverified cases: tests/fixtures/SAITAMA_RAILWAY.md and
saitama_railway_manifest.json. Third-party response bodies remain local.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, JsonValue

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_ID: Final = ProviderId("saitama_railway")
_URL: Final = "https://www.s-rail.co.jp/ticket/train/"
_FEED: Final = "https://www.s-rail.co.jp/service_status/status.json"
_LINE: Final = LineId("jp:operator_6792d0f7efc4:line_1b9213f482b7")
_STATUSES: Final = {
    "平常運転": LineStatus.NORMAL,
    "遅延": LineStatus.DELAYED,
    "運転見合わせ": LineStatus.SUSPENDED,
    "運休": LineStatus.SUSPENDED,
    "一部運休": LineStatus.PARTIAL_SUSPENSION,
    "運転再開見込": LineStatus.ALERT,
    "お知らせ": LineStatus.ALERT,
    "運転再開": LineStatus.ALERT,
    "直通運転中止": LineStatus.ALERT,
    "折返し運転": LineStatus.ALERT,
    "経路変更": LineStatus.ALERT,
    "直通運転再開": LineStatus.ALERT,
    "バス代行": LineStatus.ALERT,
    "振替輸送": LineStatus.ALERT,
    "リフレッシュ工事": LineStatus.ALERT,
    "一部運転再開": LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Saitama Railway official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_FEED, method="GET", format=DataFormat.JSON,
        description="Current messages selected by latest=true; historical entries excluded",
    ),),
    terms_url=HttpUrl("https://www.s-rail.co.jp/sitepolicy/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site policy requires the operator's consent for printing, quoting or "
        "repurposing site information (including text and data); no commercial or "
        "redistribution licence is granted. The service page covers delays of at "
        "least 15 minutes or anticipated delays and warns that published information "
        "may differ from actual operation. Only latest messages are parsed, excluding "
        "the separate history and news. Raw recordings include historical messages."
    ),
    statuses=frozenset(_STATUSES.values()),
    reviewed_at=datetime.fromisoformat("2026-11-04T13:05:02.828039+00:00"),
)


class _Header(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    # JavaScript's if (msg.latest) also excludes an absent flag.
    latest: bool = False


class _Feed(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    messages: list[dict[str, JsonValue]]


class _Japanese(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    text: str
    status: str | None = None


class _Languages(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    ja: _Japanese


class _Message(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    type: str
    time: str
    langs: _Languages


def _publication_time(value: str) -> datetime:
    if re.fullmatch(r"[0-9]{14}", value) is None:
        raise ParseError("Saitama Railway publication timestamp format changed")
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Tokyo"))


def _parse(payload: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    feed = _Feed.model_validate_json(payload)
    statuses: list[LineStatus] = []
    labels: list[str] = []
    times: list[datetime] = []
    alerts = []
    for raw_message in feed.messages:
        header = _Header.model_validate(raw_message)
        if not header.latest:
            continue
        # Validate full content only within the declared current-message scope.
        message = _Message.model_validate(raw_message)
        times.append(_publication_time(message.time))
        text = message.langs.ja.text
        if not text.strip() or not message.type.strip():
            raise ParseError("Saitama Railway current message is empty")
        if message.type == "stdtxt":
            label, status = text, LineStatus.NORMAL
        elif message.type == "message":
            label = message.langs.ja.status or ""
            if not label.strip():
                raise ParseError("Saitama Railway current status label is missing")
            status = _STATUSES.get(label, LineStatus.UNKNOWN)
        else:
            label = message.langs.ja.status or message.type
            status = LineStatus.UNKNOWN
        statuses.append(status)
        labels.append(label)
        if status is not LineStatus.NORMAL:
            alerts.append(make_alert(line, status, label, text))
    status = combined_status(tuple(statuses)) if statuses else LineStatus.UNKNOWN
    return (snapshot(
        line, status, "\n".join(labels) if labels else "運行情報はありません。", fetched_at,
        updated_at=max(times) if times else None, alerts=tuple(alerts),
    ),)


class SaitamaRailwayProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE].create_line(_ID, _URL),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
