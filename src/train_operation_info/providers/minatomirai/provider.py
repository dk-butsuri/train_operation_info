"""Minatomirai official service information.

Investigation: archived HTML and public HTML/CSS/JavaScript inspection.
https://www.mm21railway.co.jp/service/ embeds .service_information > .info.
https://www.mm21railway.co.jp/service/css/index.css renders .caution as a
generic warning, not a suspension code. common/js/common.js loads a separate
homepage popup; the service page's actual notice is already in the HTML.

Wayback originals under http://www.mm21railway.co.jp/service/:
20160920120337id_ (normal with weather advisory), 20180122144419id_
(disruption, with explicit delay field 大幅な遅れ), 20191011232736id_
(cancellations without caution), 20191012171120id_ (service ended, caution),
20221216085310id_ (normal variant). Prefix each with
https://web.archive.org/web/ to obtain the capture URL. Only the explicit
normal messages and verified delay field determine NORMAL/DELAYED. Other
notices remain ALERT; neither caution nor narrative keywords prove suspension
or partial suspension. Unknown CSS classes or contradictory normal notices
are UNKNOWN. Missing/ambiguous structure raises ParseError atomically.

The optional detail table is retained verbatim with labels, including incident
occurrence time, cause and delay. Occurrence time is not an update timestamp;
updated_at is None. Current live normal HTML and all five captures are fixtures.
Normal-after-incident tests use a separate normal capture, not same-event
recovery evidence. Unknown/malformed cases are synthetic. Distinct suspension
codes, modern abnormal HTML and same-event recovery remain unverified.
No train positions, delay certificates or linked replacement-transport lists
are fetched. Evidence/hashes: tests/fixtures/MINATOMIRAI.md and manifest.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.mm21railway.co.jp/service/"
_ID: Final = ProviderId("minatomirai")
# Same route as Yahoo 401/0; each provider keeps its own immutable snapshots.
_LINE_ID: Final = LineId("jp:operator_d2d012d773b3:line_3b169884afee")
_NORMAL: Final = frozenset((
    "みなとみらい線は、平常通り運行しています。",
    "みなとみらい線は平常通り運行しております。",
    "みなとみらい線は平常通り運行しています。",
))
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Service notice and detail table',
        ),
    ),
    provider_id=_ID, name="Minatomirai official",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.mm21railway.co.jp/info/sitepolicy.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site policy prohibits unauthorized reproduction of site content; "
        "no commercial reuse grant was found. The operation page publishes "
        "delays of 10 minutes or more or suspensions, including anticipated "
        "disruption, and warns that published information may differ from service."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T05:35:27+00:00"),
)


def _parse(html: str, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select(".service_information")
    if len(panels) != 1:
        raise ParseError("Minatomirai service panel is missing or duplicated")
    panel = panels[0]
    notices = panel.select(".info")
    if len(notices) != 1:
        raise ParseError("Minatomirai notice is missing or duplicated")
    notice = notices[0]
    body = notice.get_text("\n", strip=True)
    if not body or body == "-":
        raise ParseError("Minatomirai notice is empty")

    details: dict[str, str] = {}
    tables = panel.select("table.basic")
    if len(tables) > 1:
        raise ParseError("Minatomirai details table is duplicated")
    for table in tables:
        rows = table.select("tr")
        if not rows:
            raise ParseError("Minatomirai details table is empty")
        for row in rows:
            headings, values = row.select("th"), row.select("td")
            if len(headings) != 1 or len(values) != 1:
                raise ParseError("Minatomirai detail row is malformed")
            key = headings[0].get_text(" ", strip=True)
            value = values[0].get_text("\n", strip=True)
            if not key or not value or key in details:
                raise ParseError("Minatomirai detail is empty or duplicated")
            details[key] = value

    classes = set(notice.get_attribute_list("class"))
    if classes - {"info", "caution"}:
        state = LineStatus.UNKNOWN
    elif body in _NORMAL:
        state = LineStatus.UNKNOWN if details or "caution" in classes else LineStatus.NORMAL
    elif details.get("遅延時間") == "大幅な遅れ":
        state = LineStatus.DELAYED
    else:
        state = LineStatus.ALERT
    description = "\n".join((body, *(f"{key}：{value}" for key, value in details.items())))
    alerts = () if state is LineStatus.NORMAL else (
        make_alert(line, state, "みなとみらい線 運行情報", description),
    )
    return (snapshot(line, state, body, fetched_at, alerts=alerts),)


class MinatomiraiProvider(SnapshotProvider):
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
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
