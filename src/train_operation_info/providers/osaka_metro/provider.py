"""Osaka Metro official service alerts.

Investigation: Both archive and public-source inspection. Official HTML status-summary
markup was inspected. Wayback captures 20230815015922, 20240829220436, 20240830010545,
20240830045314 and 20260111081515 verify delays, cancellation, and recovery. The real
cancellation alt label is 'icon + unkyu', not the initially assumed suspension wording.
Detail app returned HTTP 403 and is not queried. Evidence URLs and extraction details:
tests/fixtures/README.md.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from pydantic import HttpUrl
from bs4 import BeautifulSoup, Tag

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    AlertEffect, LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider

_SOURCE_URL: Final = "https://subway.osakametro.co.jp/guide/subway_information.php"
_PROVIDER_ID: Final = ProviderId("osaka_metro")


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_SOURCE_URL, method="GET", format=DataFormat.HTML,
            description='Line status summary',
        ),
    ),
    provider_id=ProviderId('osaka_metro'), name='Osaka Metro official',
    source_page_url=HttpUrl('https://subway.osakametro.co.jp/guide/subway_information.php'),
    terms_url=HttpUrl('https://www.osakametro.co.jp/site_info.php'),
    additional_terms_urls=(HttpUrl('https://subway.osakametro.co.jp/guide/subway_information.php'), HttpUrl('https://subway.osakametro.co.jp/guide/page/readme_46_pc.php/1000'), ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='The operation page prohibits unapproved secondary use. General site terms separately reserve statutory exceptions including private copying and quotation; this metadata does not resolve an individual use case.',
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

@dataclass(frozen=True)
class _Definition:
    key: str
    name: str


_DEFINITIONS: Final = (
    _Definition("midosuji", "御堂筋線"),
    _Definition("tanimachi", "谷町線"),
    _Definition("yotsubashi", "四つ橋線"),
    _Definition("chuo", "中央線"),
    _Definition("sennichimae", "千日前線"),
    _Definition("sakaisuji", "堺筋線"),
    _Definition("nagahori_tsurumi_ryokuchi", "長堀鶴見緑地線"),
    _Definition("imazatosuji", "今里筋線"),
    _Definition("new_tram", "ニュートラム"),
)


def _initial_line(definition: _Definition) -> Line:
    identifier = LineId(f"jp:osaka_metro:{definition.key}")
    return LINE_CATALOG[identifier].create_line(_PROVIDER_ID, _SOURCE_URL)


def _attribute(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ParseError(f"Missing or invalid {name!r} in Osaka Metro status summary")
    return value.strip()


def _status(label: str) -> LineStatus:
    # Only explicit labels are accepted. An unfamiliar icon is never NORMAL.
    value = label.removeprefix("アイコン").strip()
    if value in ("通常運転", "通常運行", "平常運転"):
        return LineStatus.NORMAL
    if value in ("遅延", "遅延など"):
        return LineStatus.DELAYED
    if value in ("運転見合わせ", "運行停止", "運休"):
        return LineStatus.SUSPENDED
    return LineStatus.UNKNOWN


def _parse(html: str, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    summary = soup.select_one("dl.headerMenuOperationArea")
    if summary is None:
        raise ParseError("Osaka Metro line status summary is missing")
    time_tag = summary.select_one(".cs-currentTimeSP")
    if time_tag is None:
        raise ParseError("Osaka Metro displayed timestamp is missing")
    try:
        updated_at = datetime.strptime(
            time_tag.get_text(strip=True), "%Y/%m/%d %H:%M現在",
        ).replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    except ValueError as exc:
        raise ParseError("Invalid Osaka Metro displayed timestamp") from exc

    by_name: dict[str, str] = {}
    for row in summary.select("dd.headerMenuOperationArea_subway"):
        name_image = row.select_one(".subwayArea_LineName img")
        status_image = row.select_one(".subwayArea_Status img")
        if name_image is None or status_image is None:
            raise ParseError("Incomplete Osaka Metro line status row")
        name = _attribute(name_image, "alt")
        if name in by_name:
            raise ParseError(f"Duplicate Osaka Metro line: {name}")
        by_name[name] = _attribute(status_image, "alt")

    if set(by_name) != {definition.name for definition in _DEFINITIONS}:
        raise ParseError("Osaka Metro line list changed or is incomplete")

    lines: list[Line] = []
    for definition in _DEFINITIONS:
        initial = _initial_line(definition)
        label = by_name[definition.name]
        status = _status(label)
        alerts: tuple[ServiceAlert, ...] = ()
        if status is not LineStatus.NORMAL:
            effect = {
                LineStatus.DELAYED: AlertEffect.DELAYS,
                LineStatus.SUSPENDED: AlertEffect.NO_SERVICE,
                LineStatus.UNKNOWN: AlertEffect.UNKNOWN,
            }[status]
            alerts = (ServiceAlert(
                alert_id=f"{_PROVIDER_ID}:{initial.line_id}:{status.value}",
                title=f"{definition.name}: {label.removeprefix('アイコン')}",
                description=label,
                effect=effect,
                affected_line_ids=(initial.line_id,),
                source_url=_SOURCE_URL,
            ),)
        lines.append(Line(
            line_id=initial.line_id, name=initial.name, operator=initial.operator,
            provider_id=_PROVIDER_ID, source_url=_SOURCE_URL,
            status=status, source_status=label, alerts=alerts,
            fetched_at=fetched_at, updated_at=updated_at,
        ))
    return tuple(lines)


class OsakaMetroProvider(SnapshotProvider):
    """Read the public official summary; property access never performs I/O.

    An injected client remains owned by the caller. Without one, a temporary
    client is opened and closed for each refresh.
    """

    _metadata = _METADATA
    _provider_id = _PROVIDER_ID
    _source_url = _SOURCE_URL
    _timeout = 15.0

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(_initial_line(item) for item in _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _SOURCE_URL)
        response.raise_for_status()
        return _parse(response.text, self._now())

    @property
    def midosuji(self) -> Line:
        return self._lines[0]

    @property
    def tanimachi(self) -> Line:
        return self._lines[1]

    @property
    def yotsubashi(self) -> Line:
        return self._lines[2]

    @property
    def chuo(self) -> Line:
        return self._lines[3]

    @property
    def sennichimae(self) -> Line:
        return self._lines[4]

    @property
    def sakaisuji(self) -> Line:
        return self._lines[5]

    @property
    def nagahori_tsurumi_ryokuchi(self) -> Line:
        return self._lines[6]

    @property
    def imazatosuji(self) -> Line:
        return self._lines[7]

    @property
    def new_tram(self) -> Line:
        return self._lines[8]
