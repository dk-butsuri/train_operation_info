"""Hankyu official service alerts.

Investigation: Both archive and public-source inspection. The public page includes
/railinfo/include/page_railinfo.html; it publishes three line groups and reader-clock
JavaScript. Wayback capture 20250722023635 verifies Kyoto-group delay and restart
narrative; 20230815061839 verifies service-change notices while all group icons are
normal. Reader-clock values are not source update timestamps. Evidence:
tests/fixtures/SOURCES.md.
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
from ..base import SnapshotProvider, initial_lines, japanese_status, make_alert, snapshot

_URL: Final = "https://www.hankyu.co.jp/railinfo/include/page_railinfo.html"
_PAGE_URL: Final = "https://www.hankyu.co.jp/railinfo/index.html"
_ID: Final = ProviderId("hankyu")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:hankyu"), name="阪急電鉄")
_DEFINITIONS: Final = (("kobe", "神戸線"), ("takarazuka", "宝塚線"), ("kyoto", "京都線"))


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Line-group status HTML include',
        ),
    ),
    provider_id=ProviderId('hankyu'), name='Hankyu official',
    source_page_url=HttpUrl('https://www.hankyu.co.jp/railinfo/index.html'),
    terms_url=HttpUrl('https://www.hankyu.co.jp/sitepolicy/index.html'),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note='The site reserves uses allowed by law and requires prior permission beyond that range. This category records that statutory exception, not a separate licence for public signage or automated reuse.',
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    statuses: dict[str, str] = {}
    for row in soup.select(".sec02_inner_cnt_line"):
        name_tag, status_tag = row.select_one("h3 span"), row.select_one("p")
        if name_tag is None or status_tag is None:
            raise ParseError("Incomplete Hankyu status row")
        name = name_tag.get_text(strip=True)
        if name in statuses:
            raise ParseError("Duplicate Hankyu line group")
        statuses[name] = status_tag.get_text(strip=True)
    if set(statuses) != {line.name for line in lines}:
        raise ParseError("Hankyu line groups changed or are missing")
    result: list[Line] = []
    for line in lines:
        label = statuses[line.name]
        status = japanese_status(label)
        descriptions: list[str] = []
        for notice in soup.select(".sec03_inner_cnt"):
            text = notice.get_text("\n", strip=True)
            heading_tag = notice.select_one(".sec03_inner_ttl h2")
            heading = heading_tag.get_text(strip=True) if heading_tag is not None else ""
            if line.name in heading or f"【{line.name}】" in text or "阪急全線" in text:
                descriptions.append(text)
        description = "\n\n".join(descriptions) or label
        if status is LineStatus.NORMAL and descriptions:
            status = LineStatus.ALERT
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{line.name}: {'お知らせ' if status is LineStatus.ALERT else label}", description),
        )
        # JS #update_date is the reader's clock, not a source update timestamp.
        result.append(snapshot(line, status, label, fetched_at, alerts=alerts))
    return tuple(result)


class HankyuProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _PAGE_URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:hankyu", _ID, _PAGE_URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def kobe(self) -> Line:
        return self._line("kobe")

    @property
    def takarazuka(self) -> Line:
        return self._line("takarazuka")

    @property
    def kyoto(self) -> Line:
        return self._line("kyoto")
