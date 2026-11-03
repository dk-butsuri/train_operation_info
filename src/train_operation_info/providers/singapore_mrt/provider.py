"""Singapore LTA MyTransport MRT/LRT service alerts.

Investigation: Public-source inspection, plus the live normal JSON response.
/etc/designs/ltagov/custom/map/script.js identifies resourcePath, the public
LTAGOVTrainServiceAlerts POST request, line codes and message categories. No abnormal
archived POST response has been verified; abnormal scenarios are synthetic and labelled as
such. Preserve unknown messages/segments; do not copy the UI fallback that silently treats
unsupported messages as normal. Evidence: tests/fixtures/SOURCES.md.
The source script parses the complete HH:MM-LINE-Major/Minor/Planned header.
These categories are retained as ALERT; they do not distinguish delay from
suspension. Free prose never establishes severity, scope or recovery. Unknown
rail headers remain unscoped UNKNOWN. When Status=1, non-rail-format messages
do not override the network status; the live feed also carries bus diversions.
Status=2 and AffectedSegments still preserve unclassified disruptions. The
source filter and mixed live response are saved in tests/fixtures/mrt_manifest.json.
"""

from datetime import datetime
import re
from typing import Final
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pydantic import (
    BaseModel, ConfigDict, Field, HttpUrl,
)

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineId, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, initial_lines, make_alert, snapshot

_URL: Final = "https://www.mytransport.sg/trainstatus"
_ID: Final = ProviderId("singapore_mrt")
_SMRT: Final = Operator(operator_id=OperatorId("sg:smrt"), name="SMRT Trains")
_SBS: Final = Operator(operator_id=OperatorId("sg:sbs_transit"), name="SBS Transit")
_SMRT_DEFINITIONS: Final = (
    ("north_south", "North-South Line"), ("east_west", "East-West Line"),
    ("circle", "Circle Line"), ("thomson_east_coast", "Thomson-East Coast Line"),
    ("bukit_panjang", "Bukit Panjang LRT"),
)
_SBS_DEFINITIONS: Final = (
    ("north_east", "North East Line"), ("downtown", "Downtown Line"),
    ("sengkang", "Sengkang LRT"), ("punggol", "Punggol LRT"),
)
_CODES: Final = {
    "NSL": "north_south", "EWL": "east_west", "CCL": "circle",
    "TEL": "thomson_east_coast", "NEL": "north_east", "DTL": "downtown",
    "BPL": "bukit_panjang", "BP": "bukit_panjang",
    "STC": "sengkang", "SK": "sengkang", "SKL": "sengkang",
    "PTC": "punggol", "PG": "punggol", "PGL": "punggol",
}
_MESSAGE_HEADER: Final = re.compile(
    r"\d{2}:\d{2}-([A-Za-z0-9]+)-(Major|Minor|Planned)\b\.?\s*.*",
    re.IGNORECASE | re.DOTALL,
)
# A guard against dropping a rail-shaped message with an unsupported category.
# Matching this prefix establishes neither its scope nor its severity.
_RAIL_MESSAGE_PREFIX: Final = re.compile(r"\d{2}:\d{2}-[A-Za-z0-9]+-")


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Discovers input#resourcePath',
        ),
        SourceEndpoint(
            url="https://www.mytransport.sg/content/ltagov/{resource_path}.ltaDatamallAPI.POST.html", method="POST", format=DataFormat.JSON,
            is_template=True,
            description='resource_path is the discovered path after /content/ltagov/; form serviceName=LTAGOVTrainServiceAlerts, param is empty',
        ),
    ),
    provider_id=_ID, name='Singapore LTA MyTransport MRT/LRT',
    source_page_url=HttpUrl('https://www.mytransport.sg/trainstatus'),
    terms_url=HttpUrl('https://www.lta.gov.sg/content/ltagov/en/terms-of-use.html'),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='LTA website terms require prior written permission for reproduction and distribution except where otherwise provided. Availability of the website endpoint is not a DataMall commercial reuse licence.',
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

class _SourceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Segment(_SourceModel):
    Line: str = Field(min_length=1)
    Direction: str = ""
    Stations: str = ""


class _Message(_SourceModel):
    Content: str = Field(min_length=1)
    CreatedDate: str | None = None


class _TrainAlerts(_SourceModel):
    Status: int = Field(ge=1, le=2)
    AffectedSegments: list[_Segment]
    Message: list[_Message]


class _Envelope(_SourceModel):
    value: _TrainAlerts


def _created_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return value.replace(tzinfo=ZoneInfo("Asia/Singapore")) if value.tzinfo is None else value


def _message_code(content: str) -> str | None:
    match = _MESSAGE_HEADER.fullmatch(content.strip())
    return match.group(1).upper() if match else None


def _parse(data: _TrainAlerts, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    by_key = {line.line_id.rsplit(":", 1)[-1]: line for line in lines}
    statuses: dict[LineId, list[LineStatus]] = {line.line_id: [] for line in lines}
    labels: dict[LineId, list[str]] = {line.line_id: [] for line in lines}
    alerts: dict[LineId, list[ServiceAlert]] = {line.line_id: [] for line in lines}
    times: dict[LineId, list[datetime]] = {line.line_id: [] for line in lines}
    if data.Status == 2 and not data.AffectedSegments and not data.Message:
        raise ParseError("MyTransport reports disruption without any details")
    # Like the source UI, use the latest supported message per line. Unknown
    # formats remain unscoped and cannot establish recovery. Missing dates remain None;
    # ties without published dates use feed order, not a fabricated timestamp.
    latest_messages: dict[str, tuple[_Message, datetime | None]] = {}
    unscoped_messages: list[_Message] = []
    for entry in data.Message:
        code = _message_code(entry.Content)
        if code is None:
            # The source UI filters messages by the rail header, not by words
            # in the body. With an explicit normal network status, unrelated
            # messages (e.g. bus diversions) must not mark all rail lines UNKNOWN.
            # Preserve unsupported rail headers and every message during a
            # reported disruption rather than hiding unclassified rail alerts.
            if data.Status == 1 and not _RAIL_MESSAGE_PREFIX.match(entry.Content.strip()):
                continue
            unscoped_messages.append(entry)
            continue
        if code not in _CODES:
            raise ParseError(f"Unknown MyTransport line code: {code}")
        key = _CODES[code]
        created_at = _created_at(entry.CreatedDate)
        previous = latest_messages.get(key)
        if previous is not None and previous[1] is not None:
            if created_at is None or created_at < previous[1]:
                continue
        latest_messages[key] = (entry, created_at)
    covered: set[LineId] = set()
    for entry in (*unscoped_messages, *(item[0] for item in latest_messages.values())):
        code = _message_code(entry.Content)
        if code is not None and code not in _CODES:
            raise ParseError(f"Unknown MyTransport line code: {code}")
        targets = (by_key[_CODES[code]],) if code is not None else lines
        status = LineStatus.ALERT if code is not None else LineStatus.UNKNOWN
        affected_ids = tuple(line.line_id for line in targets) if code else ()
        alert = make_alert(
            targets[0], status, entry.Content.splitlines()[0], entry.Content,
            affected_line_ids=affected_ids, language="en",
        )
        created_at = _created_at(entry.CreatedDate)
        for line in targets:
            covered.add(line.line_id)
            statuses[line.line_id].append(status)
            labels[line.line_id].append(entry.Content)
            if status is not LineStatus.NORMAL:
                alerts[line.line_id].append(alert)
            if created_at is not None:
                times[line.line_id].append(created_at)
    for segment in data.AffectedSegments:
        code = segment.Line.upper()
        if code not in _CODES:
            raise ParseError(f"Unknown MyTransport affected segment: {code}")
        line = by_key[_CODES[code]]
        if line.line_id in covered:
            continue
        # A segment alone does not distinguish a delay from a suspension.
        description = " | ".join(filter(None, (segment.Line, segment.Direction, segment.Stations)))
        statuses[line.line_id].append(LineStatus.UNKNOWN)
        labels[line.line_id].append(description)
        alerts[line.line_id].append(make_alert(
            line, LineStatus.UNKNOWN, f"{line.name}: service alert", description, language="en",
        ))
    return tuple(snapshot(
        line, combined_status(tuple(statuses[line.line_id])),
        "\n".join(labels[line.line_id]) or "Normal (no active service alert)", fetched_at,
        updated_at=max(times[line.line_id]) if times[line.line_id] else None,
        alerts=tuple(alerts[line.line_id]),
    ) for line in lines)


class SingaporeMrtProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = (
            *initial_lines("sg:mrt", _ID, _URL, _SMRT, _SMRT_DEFINITIONS),
            *initial_lines("sg:mrt", _ID, _URL, _SBS, _SBS_DEFINITIONS),
        )
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        page = await self._get(client, _URL)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        resource = soup.select_one("input#resourcePath")
        path = resource.get("value") if resource is not None else None
        if not isinstance(path, str) or not path.startswith("/content/ltagov/") or not path.endswith("/ltaDatamallAPI"):
            raise ParseError("MyTransport resourcePath changed or is missing")
        url = urljoin(_URL, path + ".ltaDatamallAPI.POST.html")
        response = await self._post(client, url, data={"serviceName": "LTAGOVTrainServiceAlerts", "param": ""})
        response.raise_for_status()
        data = _Envelope.model_validate_json(response.content)
        return _parse(data.value, self.lines, self._now())

    @property
    def north_south(self) -> Line:
        return self._line("north_south")

    @property
    def east_west(self) -> Line:
        return self._line("east_west")

    @property
    def circle(self) -> Line:
        return self._line("circle")

    @property
    def thomson_east_coast(self) -> Line:
        return self._line("thomson_east_coast")

    @property
    def north_east(self) -> Line:
        return self._line("north_east")

    @property
    def downtown(self) -> Line:
        return self._line("downtown")

    @property
    def bukit_panjang(self) -> Line:
        return self._line("bukit_panjang")

    @property
    def sengkang(self) -> Line:
        return self._line("sengkang")

    @property
    def punggol(self) -> Line:
        return self._line("punggol")
