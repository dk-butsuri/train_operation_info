"""Nagoya Municipal Subway official service alerts.

Investigation: public JavaScript inspection and a live normal JSON response.
https://www.kotsu.city.nagoya.jp/rp/emergency/ loads
https://www.kotsu.city.nagoya.jp/rp/Jassets/js/common/traffic_info_for_top.js.
It fetches /datas/latest_traffic.json and displays every slot by rosen_id.
The script maps N/W/C/E_T_ICO to normal/delay/caution/suspended CSS classes.
N_T_ICO is NORMAL only with the exact title 平常運行; other normal-icon
titles are notices (ALERT), as in the script's お知らせあり branch.
C_T_ICO is ALERT without an inferred specific effect. Unknown icons stay
UNKNOWN. Message, cause, section and dates never determine classification.

M_LINE covers both Meijo and Meiko; all five existing Yahoo canonical IDs
are reused. B_LINE is excluded before validating its content, but raw HTTP
recordings include bus data. No separate long-term category is exposed;
all subway slots are retained. The icon alone does not establish timing,
so timing remains UNKNOWN. create_datetime is a publication field without
an offset, not a confirmed route update time: updated_at and applicability
dates remain None. The page's browser-generated display clock is unused.

Wayback CDX returned no captures for this JSON URL. Real disruption and
recovery responses remain unverified; those tests are synthetic, based on
the public script. Evidence URLs, UTC retrieval times, hashes and extraction:
tests/fixtures/NAGOYA_SUBWAY.md and nagoya_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, TypeAdapter, field_validator

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_URL: Final = "https://www.kotsu.city.nagoya.jp/rp/emergency/"
_FEED_URL: Final = "https://www.kotsu.city.nagoya.jp/datas/latest_traffic.json"
_ID: Final = ProviderId("nagoya_subway")
# Official rosen_id -> existing canonical ID. M_LINE is a combined system.
_BINDINGS: Final = (
    ("H_LINE", LineId("jp:operator_f28d789a1fa7:line_f2d919c931ae")),
    ("M_LINE", LineId("jp:operator_f28d789a1fa7:line_205e60be39e6")),
    ("T_LINE", LineId("jp:operator_f28d789a1fa7:line_ce492247f6f9")),
    ("S_LINE", LineId("jp:operator_f28d789a1fa7:line_0330f591536d")),
    ("K_LINE", LineId("jp:operator_f28d789a1fa7:line_f3aba768460b")),
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Nagoya Municipal Subway official",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_FEED_URL, method="GET", format=DataFormat.JSON,
        description="All subway slots in latest_traffic.json; B_LINE bus content is excluded",
    ),),
    terms_url=HttpUrl("https://www.kotsu.city.nagoya.jp/rp/WEBSITE/trp0000834.htm"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site terms prohibit reproduction and republication without the "
        "Transportation Bureau's permission. The operation-page footer also "
        "prohibits unauthorised use and republication. No separate reuse grant "
        "for this JSON was found. Subway information is provided when delays "
        "of ten minutes or more are expected; NORMAL is within that coverage."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-03T16:02:05+00:00"),
)


class _Route(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    rosen_id: str


class _Traffic(_Route):
    traffic_no: int
    slot_no: int
    icon_cd: str
    traffic_title: str
    traffic_message: str | None
    traffic_section: str | None
    traffic_cause: str | None

    @field_validator("icon_cd", "traffic_title")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Empty Nagoya subway status")
        return value


_ROWS: Final = TypeAdapter(list[object])


def _status(row: _Traffic) -> LineStatus:
    if row.icon_cd == "N_T_ICO":
        return LineStatus.NORMAL if row.traffic_title == "平常運行" else LineStatus.ALERT
    return {
        "W_T_ICO": LineStatus.DELAYED,
        "C_T_ICO": LineStatus.ALERT,
        "E_T_ICO": LineStatus.SUSPENDED,
    }.get(row.icon_cd, LineStatus.UNKNOWN)


def _description(row: _Traffic) -> str:
    # These are separate display fields in UpdateTrafficInfoForDetail.
    return "\n".join(
        prefix + value for prefix, value in (
            ("", row.traffic_message), ("区間：", row.traffic_section),
            ("理由：", row.traffic_cause),
        ) if value and value != "null"
    )


def _parse(payload: bytes, fetched_at: datetime) -> tuple[Line, ...]:
    by_route: dict[str, list[_Traffic]] = {code: [] for code, _ in _BINDINGS}
    slots: set[tuple[str, int]] = set()
    identifiers: set[int] = set()
    # The live feed has a UTF-8 BOM.
    for raw in _ROWS.validate_json(payload.decode("utf-8-sig")):
        route = _Route.model_validate(raw)
        if route.rosen_id == "B_LINE":
            continue
        if route.rosen_id not in by_route:
            raise ParseError(f"Unknown Nagoya subway route: {route.rosen_id}")
        row = _Traffic.model_validate(raw)
        slot = (row.rosen_id, row.slot_no)
        if slot in slots or row.traffic_no in identifiers:
            raise ParseError("Duplicate Nagoya subway slot or traffic number")
        slots.add(slot)
        identifiers.add(row.traffic_no)
        by_route[row.rosen_id].append(row)
    if any(not rows for rows in by_route.values()):
        raise ParseError("Incomplete Nagoya subway route list")

    lines: list[Line] = []
    for code, line_id in _BINDINGS:
        line = LINE_CATALOG[line_id].create_line(_ID, _URL)
        rows = by_route[code]
        statuses = tuple(_status(row) for row in rows)
        alerts = tuple(
            make_alert(
                line, status, row.traffic_title, _description(row),
                alert_id=f"{_ID}:{row.traffic_no}",
            )
            for row, status in zip(rows, statuses) if status is not LineStatus.NORMAL
        )
        lines.append(snapshot(
            line, combined_status(statuses),
            "\n".join(f"{row.icon_cd}: {row.traffic_title}" for row in rows),
            fetched_at, alerts=alerts,
        ))
    return tuple(lines)


class NagoyaSubwayProvider(SnapshotProvider):
    """Official subway feed; Meijo/Meiko remain one published system."""

    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[line_id].create_line(_ID, _URL) for _, line_id in _BINDINGS
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED_URL)
        response.raise_for_status()
        return _parse(response.content, self._now())

    @property
    def higashiyama(self) -> Line:
        return self._lines[0]

    @property
    def meijo_meiko(self) -> Line:
        return self._lines[1]

    @property
    def tsurumai(self) -> Line:
        return self._lines[2]

    @property
    def sakuradori(self) -> Line:
        return self._lines[3]

    @property
    def kamiiida(self) -> Line:
        return self._lines[4]
