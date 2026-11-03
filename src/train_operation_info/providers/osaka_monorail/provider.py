"""Osaka Monorail official service alerts.

Investigation: Public-source inspection for abnormal handling; normal archive cross-check
only. The live .operationStatus summary and Wayback capture 20250811060448 were inspected.
Standing publication-policy text and the reader clock must be excluded. No abnormal
archived sample has been found; non-normal responses are preserved as unscoped UNKNOWN
notices and tested with synthetic HTML. Evidence: tests/fixtures/SOURCES.md.
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

_URL: Final = "https://www.osaka-monorail.co.jp/"
_ID: Final = ProviderId("osaka_monorail")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:osaka_monorail"), name="大阪モノレール")
_DEFINITIONS: Final = (("main", "大阪モノレール線"), ("saito", "彩都線"))


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Network status summary',
        ),
    ),
    provider_id=ProviderId('osaka_monorail'), name='Osaka Monorail official',
    source_page_url=HttpUrl('https://www.osaka-monorail.co.jp/'),
    terms_url=HttpUrl('https://www.osaka-monorail.co.jp/siteguide/'),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='The copyright section prohibits copying or republication in other media without permission. No separate private or commercial data reuse grant was found.',
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.select_one(".operationStatus .operationStatus__status")
    if tag is None:
        raise ParseError("Osaka Monorail official status is missing")
    # Exclude the standing publication policy, English duplicate, and reader clock.
    for extra in tag.select(".-read, .-small, #dispTime"):
        extra.decompose()
    label = tag.get_text("\n", strip=True)
    if not label:
        raise ParseError("Osaka Monorail official status is empty")
    normal = label == "現在、平常通り運行しております。"
    status = LineStatus.NORMAL if normal else LineStatus.UNKNOWN
    alerts = () if normal else (make_alert(
        lines[0], status, "大阪モノレール 運行情報", label, affected_line_ids=(),
    ),)
    return tuple(snapshot(line, status, label, fetched_at, alerts=alerts) for line in lines)


class OsakaMonorailProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:osaka_monorail", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")

    @property
    def saito(self) -> Line:
        return self._line("saito")
