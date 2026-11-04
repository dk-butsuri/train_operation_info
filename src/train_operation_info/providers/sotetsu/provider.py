"""Sotetsu's official network service notice.

Investigation: public HTML/JavaScript inspection and archived official JSON.
https://www.sotetsu.co.jp/train/status/ configures trainStatusAPIURL as
https://cdn.sotetsu.co.jp/unkou/dat. Its /_nuxt/Cq7Xtqw3.js reads
train_status1_v2.json and displays MSG as 運行情報 and MSG2 as 振替輸送.
/_nuxt/BG3P_7p2.js passes IRREGULAR through unchanged; the navigation in
/_nuxt/BB6XB0j6.js labels true as 相鉄線運行情報あり and false as 相鉄線平常運転.
These map to ALERT and NORMAL, respectively. English E_STATUS is not used
by this Japanese view and has no verified exhaustive impact-code mapping.
Neither it nor narrative keywords determine DELAYED or SUSPENDED.

Wayback originals (prefix https://web.archive.org/web/):
20230717075741id_/https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json
verifies IRREGULAR=true for cancelled Toyoko through service while Meguro
through service continues. 20230729083512 and 20260519070818 at the same
original URL verify false/normal; they are later normal captures, not proof
of same-event recovery. Current normal JSON was also captured live.
MSG2 abnormal content, independent full suspension, current abnormal JSON,
multiple records and same-event recovery remain unverified. Synthetic tests
cover replacement transport, future prose, malformed data and recovery.

The single Japanese entry covers the existing canonical 相鉄線; it does not
provide a structured Japanese per-line impact. Separate 本線/いずみ野線/新横浜線
states are not invented. DATE is converted to a date by the source normalizer
but not displayed; the page's 現在 clock is new Date(Date.now()). Neither is
confirmed as a publication/update timestamp, so updated_at stays None.
No dedicated applicability state is established: timing stays UNKNOWN and
active_from/active_until remain unset, including anticipated disruptions.

Only this feed is fetched. Structurally separate owabi.json and microCMS
train-alerts (電車のお知らせ), certificates, positions and other-company notices
are excluded. NORMAL describes only this feed's 10-minute/anticipated-delay
and suspension publication scope. Provenance, hashes and terms:
tests/fixtures/SOTETSU.md and sotetsu_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, TypeAdapter

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.sotetsu.co.jp/train/status/"
_FEED: Final = "https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json"
_ID: Final = ProviderId("sotetsu")
# Same publication unit as Yahoo 125/0; source snapshots remain independent.
_LINE_ID: Final = LineId("jp:sotetsu:line_bcfb80c3830e")
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Sotetsu official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_FEED, method="GET", format=DataFormat.JSON,
        description="Japanese network service notice and replacement-transport text",
    ),),
    terms_url=HttpUrl("https://www.sotetsu.co.jp/terms/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The service page prohibits unauthorised reproduction/copying of service "
        "information. General terms reserve statutory private use and prior consent; "
        "no commercial reuse grant was found. The feed covers 10-minute or greater "
        "delays, suspensions and anticipated disruption. Separate apologies and "
        "train announcements are not fetched."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T04:53:59+00:00"),
)


class _Notice(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    MSG: str
    IRREGULAR: bool
    # The official normalizer explicitly uses MSG2 || "".
    MSG2: str = ""


_NOTICES: Final = TypeAdapter(list[_Notice])


def _parse(payload: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    notices = _NOTICES.validate_json(payload, strict=True)
    if len(notices) != 1:
        raise ParseError("Sotetsu service entry is missing or duplicated")
    notice = notices[0]
    if not notice.MSG.strip():
        raise ParseError("Sotetsu service notice is empty")
    status = LineStatus.ALERT if notice.IRREGULAR else LineStatus.NORMAL
    description = notice.MSG
    if notice.MSG2.strip():
        description += "\n振替輸送：" + notice.MSG2
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, "相鉄線 運行情報", description),
    )
    return (snapshot(line, status, description, fetched_at, alerts=alerts),)


class SotetsuProvider(SnapshotProvider):
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
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
