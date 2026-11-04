"""Renfe's official Cercanías/Rodalies GTFS-realtime notice feed, as a GROUP.

Investigation: official dataset documentation and live JSON/protobuf/static GTFS
retrieved 2026-11-04 UTC; no archive or real empty/recovery capture verified.
https://data.renfe.com/es/dataset/incidencias-avisos lists alerts.json/alerts.pb
and describes accessibility, replacement buses and track incidents. JSON schema:
https://gtfs.org/documentation/realtime/reference/ and protobuf JSON mapping
https://protobuf.dev/programming-guides/json/ (uint64 timestamps are strings,
absent repeated fields are empty, omitted incrementality means FULL_DATASET).

The captured feed has 69 entities, descriptionText but no headerText or effect,
and timestamp 2026-10-07T07:32:52Z despite retrieval on November 4. Retain that
timestamp as updated_at; never substitute fetched_at or claim ACTIVE timing.
activePeriod is a display window, not an incident interval. No prose or ID prefix
is classified. Planned/long-duration and station notices are mixed in the same
list and retained. AVE/long-distance, train delays and linked pages are excluded.

The static routes.txt at
https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip does not
resolve many live selectors. No prefix/suffix heuristics or stop-to-line guesses
are used: the single canonical es:renfe:cercanias GROUP is the dataset's network
scope, affected_line_ids=(), line status UNKNOWN when any notice exists. An empty
validated FULL_DATASET means NORMAL only within this notice publication scope.
Absent/unrecognised effects remain UNKNOWN; recognised GTFS effects map directly
to alert effects, never to the operational status of the entire network.

The source repeats one entity ID with distinct informedEntity lists. Preserve
both occurrences using source ID plus SHA-256 of the validated selector set;
duplicate ID/selector pairs fail atomically. The shared binary decoder remains
strict and unchanged. All es-labelled translations are retained in source order,
separated by blank lines: the source sometimes labels two distinct translations
as es. We do not guess their actual languages. Other labels are outside the
exposed scope. Empty/recovery, explicit effects, malformed and refusal cases
are synthetic. Provenance, hashes and limits: tests/fixtures/RENFE.md and
renfe_manifest.json. Captures are local only, never redistributed.
"""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, AlertEffect, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, snapshot

_PAGE: Final = "https://data.renfe.com/es/dataset/incidencias-avisos"
_FEED: Final = "https://gtfsrt.renfe.com/alerts.json"
_ID: Final = ProviderId("renfe")
_LINE: Final = LineId("es:renfe:cercanias")
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Renfe Cercanías / Rodalies official notices",
    source_page_url=HttpUrl(_PAGE),
    endpoints=(SourceEndpoint(
        url=_FEED, method="GET", format=DataFormat.JSON,
        description="GTFS-realtime JSON FULL_DATASET; all network and station notices retained.",
    ),),
    terms_url=HttpUrl("https://data.renfe.com/es/legal"),
    additional_terms_urls=(HttpUrl("https://creativecommons.org/licenses/by/4.0/"),),
    usage_permission=UsagePermission.COMMERCIAL_ALLOWED,
    usage_note=(
        "The dataset lists CC BY 4.0; the portal permits commercial and noncommercial "
        "reuse. Attribute 'Origen de los datos: Renfe Operadora', retain the source "
        "update date and reuse metadata, preserve meaning, and do not imply Renfe "
        "endorsement. Include the licence link and identify modifications under "
        "CC BY 4.0. Selection of es-labelled text and network aggregation are library "
        "presentation choices. Covers Cercanías/Rodalies published notices only; "
        "the observed feed timestamp is stale, so inspect updated_at as well as fetched_at."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T11:57:22.562098+00:00"),
)


class _SourceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Translation(_SourceModel):
    text: str
    language: str = ""


class _Text(_SourceModel):
    translation: list[_Translation]

    def es_text(self) -> str:
        matches = [item.text for item in self.translation if item.language == "es" and item.text.strip()]
        if not matches:
            raise ParseError("Renfe notice must contain nonempty es-labelled translations")
        return "\n\n".join(matches)


class _Trip(_SourceModel):
    tripId: str | None = None
    routeId: str | None = None
    directionId: int | None = None
    startTime: str | None = None
    startDate: str | None = None
    scheduleRelationship: str | None = None


class _Selector(_SourceModel):
    agencyId: str | None = None
    routeId: str | None = None
    routeType: int | None = None
    stopId: str | None = None
    directionId: int | None = None
    trip: _Trip | None = None


class _Period(_SourceModel):
    start: str | None = Field(default=None, pattern=r"^[0-9]+$")
    end: str | None = Field(default=None, pattern=r"^[0-9]+$")


class _Alert(_SourceModel):
    informedEntity: list[_Selector] = Field(min_length=1)
    descriptionText: _Text | None = None
    headerText: _Text | None = None
    effect: str | None = None
    activePeriod: list[_Period] = Field(default_factory=list)


class _Entity(_SourceModel):
    id: str = Field(min_length=1)
    isDeleted: Literal[False] = False
    alert: _Alert


class _Header(_SourceModel):
    gtfsRealtimeVersion: Literal["2.0"]
    incrementality: Literal["FULL_DATASET"] = "FULL_DATASET"
    timestamp: str = Field(pattern=r"^[0-9]+$")


class _Feed(_SourceModel):
    header: _Header
    entity: list[_Entity] = Field(default_factory=list)


def _parse(payload: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    feed = _Feed.model_validate_json(payload)
    try:
        updated_at = datetime.fromtimestamp(int(feed.header.timestamp), timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ParseError("Renfe source timestamp is outside the supported range") from exc
    alerts: list[ServiceAlert] = []
    identifiers: set[str] = set()
    for entity in feed.entity:
        if not entity.id.strip():
            raise ParseError("Renfe notice ID is blank")
        notice = entity.alert
        # Selector order carries no meaning. Keep distinct source scopes, even
        # when Renfe assigns them the same FeedEntity.id and identical prose.
        selectors = "\n".join(sorted({s.model_dump_json() for s in notice.informedEntity}))
        identifier = f"renfe:{entity.id}:{sha256(selectors.encode()).hexdigest()}"
        if identifier in identifiers:
            raise ParseError("Renfe notice ID and selectors duplicated")
        identifiers.add(identifier)
        description = "" if notice.descriptionText is None else notice.descriptionText.es_text()
        title = entity.id if notice.headerText is None else notice.headerText.es_text()
        if notice.headerText is None and not description:
            raise ParseError("Renfe notice has no text")
        effect = {
            "NO_SERVICE": AlertEffect.NO_SERVICE,
            "REDUCED_SERVICE": AlertEffect.REDUCED_SERVICE,
            "SIGNIFICANT_DELAYS": AlertEffect.DELAYS,
            "UNKNOWN_EFFECT": AlertEffect.UNKNOWN,
        }.get(notice.effect or "", AlertEffect.OTHER if notice.effect in {
            "DETOUR", "ADDITIONAL_SERVICE", "MODIFIED_SERVICE", "OTHER_EFFECT",
            "STOP_MOVED", "NO_EFFECT", "ACCESSIBILITY_ISSUE",
        } else AlertEffect.UNKNOWN)
        alerts.append(ServiceAlert(
            alert_id=identifier, title=title, description=description, effect=effect,
            affected_line_ids=(), source_url=_PAGE, language="es",
        ))
    return (snapshot(
        line, LineStatus.UNKNOWN if alerts else LineStatus.NORMAL,
        "Published notices" if alerts else "no alert in scope", fetched_at,
        updated_at=updated_at, alerts=tuple(alerts),
    ),)


class RenfeProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE].create_line(_ID, _PAGE),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return _parse(response.content, self.cercanias, self._now())

    @property
    def cercanias(self) -> Line:
        return self._line("cercanias")
