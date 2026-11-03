"""Hanshin official service alerts.

Investigation: Both archive and public-source inspection. The homepage contains a
navigation link and a separate real network-status span; do not mistake the navigation
icon for normal service. Wayback capture 20240830120316 contains an unscoped operation
notice, while 20250730092425 is normal. Neither proves line-specific delay or suspension
labels, so notices retain UNKNOWN line scope. Evidence: tests/fixtures/SOURCES.md.
"""

from datetime import datetime
from typing import Final

from pathlib import Path

import httpx
from pydantic import HttpUrl
from bs4 import BeautifulSoup

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, initial_lines, make_alert, snapshot

_URL: Final = "https://www.hanshin.co.jp/"
_ID: Final = ProviderId("hanshin")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:hanshin"), name="阪神電気鉄道")
_DEFINITIONS: Final = (
    ("main", "阪神本線"), ("namba", "阪神なんば線"), ("mukogawa", "武庫川線"),
)


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Network status summary',
        ),
    ),
    provider_id=ProviderId('hanshin'), name='Hanshin official',
    source_page_url=HttpUrl('https://www.hanshin.co.jp/'),
    terms_url=HttpUrl('https://www.hanshin.co.jp/terms/'),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note='Section 4 reserves the legally permitted range and requires prior consent for uses beyond it. This is not a commercial reuse licence or a finding that a particular signage use is private use.',
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    # The header has another message link labelled simply '運行情報'.
    labels = [
        tag.get_text(" ", strip=True) for tag in soup.select(".info-area__message__link")
        if tag.select_one("span") is not None
    ]
    if len(labels) != 1 or not labels[0]:
        raise ParseError("Hanshin official network status is missing or ambiguous")
    label = labels[0]
    normal = label == "現在、30分以上の列車の遅れはございません。"
    status = LineStatus.NORMAL if normal else LineStatus.UNKNOWN
    # The homepage does not identify affected lines. Preserve the notice with
    # an empty scope rather than inventing per-line delays or suspensions.
    alerts = () if normal else (make_alert(
        lines[0], status, "阪神電車 運行情報", label, affected_line_ids=(),
    ),)
    return tuple(snapshot(line, status, label, fetched_at, alerts=alerts) for line in lines)


class HanshinProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:hanshin", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")

    @property
    def namba(self) -> Line:
        return self._line("namba")

    @property
    def mukogawa(self) -> Line:
        return self._line("mukogawa")
