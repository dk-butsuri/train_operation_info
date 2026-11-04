"""TfL Unified API current rail/tram line statuses (Powered by TfL Open Data).

Investigation: official public API, Swagger schema, severity metadata and live
status page on 2026-11-04; no archived abnormal response was used. Anonymous
requests with the library User-Agent returned all 20 lines without a key.
https://api.tfl.gov.uk/swagger/docs/v1 documents Line/Mode/{modes}/Status,
Line/Meta/Severity and ValidityPeriod.isNow (realtime rather than planned/info).
The captured severity metadata establishes the exact code/label pairs below
for all five selected modes. Live data verifies Good Service, Severe/Minor
Delays, Part Suspended and Part Closure, including simultaneous statuses;
a second actual Provider refresh also verifies Suspended on Lioness.
Other mappings are specification-backed, with synthetic tests, not observed
incidents. Unknown code/label pairs remain UNKNOWN, with the original kept.

Only the undated current-status endpoint is requested. All its lineStatuses
are retained, including PlannedWork: that category does not identify duration
or distinguish long-term notices from other works. No long-term-only field is
available in this list. isNow=false also occurs on current planned works, so
it neither means future nor licenses dropping a notice. Only isNow=true on a
known non-normal status gives ACTIVE; otherwise timing stays UNKNOWN. Each
validity period is a separate alert; disjoint periods are never joined. No
date comparisons or narrative classification override the source status.

Line.created/modified describe line records, and status.created is a sentinel
in the capture. None establishes a displayed status update, so updated_at
stays None. Nested affectedRoutes/stops are outside the common line model;
the parent line identifies the affected line, never other lines mentioned in
the reason. Separate date-range/future endpoints, station/accessibility feeds,
bus, river, cable car, National Rail and arrivals are not fetched.

DLR and Tram each cover a whole network (GROUP); Overground uses its six named
lines, not the obsolete single london-overground ID. Canonical IDs describe
networks independently of the current operating concession. Actual operators
were checked separately in official TfL material; TfL is the data source.
Recovery, malformed responses and transport failures are synthetic tests.
Evidence, licence conditions, retrieval dates and hashes: tests/fixtures/TFL.md
and tfl_manifest.json. Captured third-party bodies remain local.
"""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Final

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, model_validator

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    AlertTiming, DataFormat, LINE_CATALOG, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_ID: Final = ProviderId("tfl")
_PAGE: Final = "https://tfl.gov.uk/tube-dlr-overground/status/"
_URL: Final = "https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line,tram/Status"
# Source ID -> canonical ID, expected transport mode. Order is the public API order.
_LINES: Final = {
    "bakerloo": ("gb:london_underground:bakerloo", "tube"),
    "central": ("gb:london_underground:central", "tube"),
    "circle": ("gb:london_underground:circle", "tube"),
    "district": ("gb:london_underground:district", "tube"),
    "dlr": ("gb:dlr:network", "dlr"),
    "elizabeth": ("gb:elizabeth_line:main", "elizabeth-line"),
    "hammersmith-city": ("gb:london_underground:hammersmith_city", "tube"),
    "jubilee": ("gb:london_underground:jubilee", "tube"),
    "liberty": ("gb:london_overground:liberty", "overground"),
    "lioness": ("gb:london_overground:lioness", "overground"),
    "metropolitan": ("gb:london_underground:metropolitan", "tube"),
    "mildmay": ("gb:london_overground:mildmay", "overground"),
    "northern": ("gb:london_underground:northern", "tube"),
    "piccadilly": ("gb:london_underground:piccadilly", "tube"),
    "suffragette": ("gb:london_overground:suffragette", "overground"),
    "tram": ("gb:london_trams:network", "tram"),
    "victoria": ("gb:london_underground:victoria", "tube"),
    "waterloo-city": ("gb:london_underground:waterloo_city", "tube"),
    "weaver": ("gb:london_overground:weaver", "overground"),
    "windrush": ("gb:london_overground:windrush", "overground"),
}
_STATES: Final = {
    (0, "Special Service"): LineStatus.ALERT,
    (1, "Closed"): LineStatus.SUSPENDED,
    (2, "Suspended"): LineStatus.SUSPENDED,
    (3, "Part Suspended"): LineStatus.PARTIAL_SUSPENSION,
    (4, "Planned Closure"): LineStatus.ALERT,
    (5, "Part Closure"): LineStatus.PARTIAL_SUSPENSION,
    (6, "Severe Delays"): LineStatus.DELAYED,
    (7, "Reduced Service"): LineStatus.PARTIAL_SUSPENSION,
    (8, "Bus Service"): LineStatus.ALERT,
    (9, "Minor Delays"): LineStatus.DELAYED,
    (10, "Good Service"): LineStatus.NORMAL,
    (11, "Part Closed"): LineStatus.PARTIAL_SUSPENSION,
    (12, "Exit Only"): LineStatus.ALERT,
    (13, "No Step Free Access"): LineStatus.ALERT,
    (14, "Change of frequency"): LineStatus.ALERT,
    (15, "Diverted"): LineStatus.ALERT,
    (16, "Not Running"): LineStatus.SUSPENDED,
    (17, "Issues Reported"): LineStatus.ALERT,
    (18, "No Issues"): LineStatus.NORMAL,
    (19, "Information"): LineStatus.ALERT,
    # End of operating hours is not evidence of an unplanned suspension.
    (20, "Service Closed"): LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Transport for London (TfL)", source_page_url=HttpUrl(_PAGE),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.JSON,
        description="Current statuses of Tube, DLR, six Overground lines, Elizabeth line and Tram",
    ),),
    terms_url=HttpUrl("https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service"),
    additional_terms_urls=(HttpUrl("https://api-portal.tfl.gov.uk/products"),),
    usage_permission=UsagePermission.COMMERCIAL_ALLOWED,
    usage_note=(
        "TfL's amended Open Government Licence permits commercial and non-commercial "
        "reuse subject to its conditions, including 'Powered by TfL Open Data', "
        "OS/Geomni attribution where applicable, branding and non-endorsement. "
        "The licence states commencement on registration; the API portal separately "
        "allows anonymous access at 50 requests/minute. Anonymous technical access "
        "does not settle the licence's registration condition. Review the full terms "
        "before reuse. This provider makes one request per refresh, without credentials."
    ),
    statuses=frozenset(_STATES.values()),
    reviewed_at=datetime.fromisoformat("2026-11-04T13:00:00+00:00"),
)


class _SourceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Period(_SourceModel):
    fromDate: AwareDatetime
    toDate: AwareDatetime
    isNow: bool

    @model_validator(mode="after")
    def _ordered(self) -> "_Period":
        if self.toDate < self.fromDate:
            raise ValueError("TfL validity period ends before it starts")
        return self


class _Status(_SourceModel):
    statusSeverity: int
    statusSeverityDescription: Annotated[str, Field(min_length=1)]
    reason: str | None = None
    lineId: str | None = None
    validityPeriods: list[_Period]


class _SourceLine(_SourceModel):
    id: str
    name: Annotated[str, Field(min_length=1)]
    modeName: str
    lineStatuses: Annotated[list[_Status], Field(min_length=1)]


_ADAPTER: Final = TypeAdapter(list[_SourceLine])


def _alerts(line: Line, item: _Status, state: LineStatus) -> tuple[ServiceAlert, ...]:
    if state is LineStatus.NORMAL and not item.reason:
        return ()
    alerts: list[ServiceAlert] = []
    periods: tuple[_Period | None, ...] = tuple(item.validityPeriods) or (None,)
    for period in periods:
        identity = f"{line.line_id}:{item.model_dump_json()}:{period.model_dump_json() if period else ''}"
        alert = make_alert(
            line, state, f"{line.name}: {item.statusSeverityDescription}",
            item.reason if item.reason is not None else item.statusSeverityDescription,
            alert_id=sha256(identity.encode()).hexdigest()[:24], language="en",
            timing=(AlertTiming.ACTIVE if period is not None and period.isNow
                    and state not in (LineStatus.UNKNOWN, LineStatus.NORMAL)
                    else AlertTiming.UNKNOWN),
        )
        alerts.append(alert.model_copy(update={
            "active_from": period.fromDate if period else None,
            "active_until": period.toDate if period else None,
        }))
    return tuple(alerts)


def _parse(body: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    data = _ADAPTER.validate_json(body)
    by_id = {item.id: item for item in data}
    if len(by_id) != len(data) or set(by_id) != set(_LINES):
        raise ParseError("TfL line set is missing, duplicated or changed")
    result: list[Line] = []
    for line, (source_id, (_, mode)) in zip(lines, _LINES.items(), strict=True):
        item = by_id[source_id]
        if item.modeName != mode:
            raise ParseError(f"TfL transport mode changed for {source_id}")
        states: list[LineStatus] = []
        alerts: list[ServiceAlert] = []
        for status in item.lineStatuses:
            if status.lineId is not None and status.lineId != source_id:
                raise ParseError(f"TfL status refers to another line: {status.lineId}")
            state = _STATES.get((status.statusSeverity, status.statusSeverityDescription), LineStatus.UNKNOWN)
            states.append(state)
            alerts.extend(_alerts(line, status, state))
        result.append(snapshot(
            line, combined_status(tuple(states)),
            "; ".join(f"{s.statusSeverity}: {s.statusSeverityDescription}" for s in item.lineStatuses),
            fetched_at, alerts=tuple(alerts), source_line_names=(item.name,),
        ))
    return tuple(result)


class TflProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[LineId(identifier)].create_line(_ID, _PAGE)
            for identifier, _ in _LINES.values()
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    def _source_line(self, source_id: str) -> Line:
        line = self.get_line(LineId(_LINES[source_id][0]))
        if line is None:
            raise KeyError(source_id)
        return line

    @property
    def bakerloo(self) -> Line:
        return self._source_line("bakerloo")

    @property
    def central(self) -> Line:
        return self._source_line("central")

    @property
    def circle(self) -> Line:
        return self._source_line("circle")

    @property
    def district(self) -> Line:
        return self._source_line("district")

    @property
    def dlr(self) -> Line:
        return self._source_line("dlr")

    @property
    def elizabeth(self) -> Line:
        return self._source_line("elizabeth")

    @property
    def hammersmith_city(self) -> Line:
        return self._source_line("hammersmith-city")

    @property
    def jubilee(self) -> Line:
        return self._source_line("jubilee")

    @property
    def liberty(self) -> Line:
        return self._source_line("liberty")

    @property
    def lioness(self) -> Line:
        return self._source_line("lioness")

    @property
    def metropolitan(self) -> Line:
        return self._source_line("metropolitan")

    @property
    def mildmay(self) -> Line:
        return self._source_line("mildmay")

    @property
    def northern(self) -> Line:
        return self._source_line("northern")

    @property
    def piccadilly(self) -> Line:
        return self._source_line("piccadilly")

    @property
    def suffragette(self) -> Line:
        return self._source_line("suffragette")

    @property
    def tram(self) -> Line:
        return self._source_line("tram")

    @property
    def victoria(self) -> Line:
        return self._source_line("victoria")

    @property
    def waterloo_city(self) -> Line:
        return self._source_line("waterloo-city")

    @property
    def weaver(self) -> Line:
        return self._source_line("weaver")

    @property
    def windrush(self) -> Line:
        return self._source_line("windrush")
