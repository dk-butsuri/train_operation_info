"""MTA New York City Subway: official keyless GTFS-realtime Service Alerts feed.

Investigation: official documentation plus one live protobuf response; no
archive. The feed URL is listed on https://api.mta.info/ and needs no API key.
"MTA GTFS Alerts Feed Documentation" (December 2021,
https://www.mta.info/document/90881) defines the MTA usage:
- FeedEntity.id "lmm:planned_work..." is a planned service interruption
  (maintenance, repairs, upgrades) and "lmm:alert..." an unplanned disruption.
  Planned work is therefore structurally separated and excluded; the Mercury
  alert_type is not used for this because the documentation says to treat it as
  free text, and live planned-work entities include types without a "Planned -"
  prefix (Reduced Service, Boarding Change, Extra Service, Station Notice,
  Expect Delays). Other "lmm:" entities are kept as they are; an ID without the
  documented "lmm:" prefix is rejected.
- cause, effect and url are "not currently used". Every kept alert is therefore
  UNKNOWN under the shared GTFS-rt rules in providers/gtfs_rt.py; the free-text
  alert_type and Mercury sort_order priorities are not decoded or classified,
  although https://www.mta.info/guides/service-status describes the labels.
- active_period is "when the alert should be shown to the user"; unplanned
  alerts have only a start equal to the Mercury creation time. It is not an
  incident period, so active_from/active_until stay None and timing UNKNOWN.
- EntitySelector carries agency_id MTASBWY with route_id or stop_id. route_id
  values were verified against routes.txt of the official static GTFS
  https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip (2026-11-03, 29 routes,
  agency "MTA NYCT"). Each GTFS route (a service such as A, 6X or GS) is one
  canonical line; unregistered route_ids fail the refresh atomically.
Live capture 2026-11-03T03:33:16Z: 180 entities, 178 planned work and two
unplanned alerts (Delays on F/G, Stops Skipped on B/Q), all route-only selectors
without effect. A second capture at 2026-11-03T04:53:54Z shows those F/G/B
alerts removed (real recovery) and new Delays alerts on Q, 3 and E whose
active_period now has an end, again without effect. NORMAL means no unplanned
alert for the route; it does not mean there is no planned work. Stop-only
selectors, explicit effects and malformed feeds are synthetic tests.
See tests/fixtures/MTA_SUBWAY.md and mta_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider
from ..gtfs_rt import FeedEntity, FeedScope, decode_feed, lines_from_feed

# The home page shows per-line service status; /alerts lists planned changes.
_PAGE: Final = "https://www.mta.info/"
_FEED: Final = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts"
_ID: Final = ProviderId("mta_subway")
# GTFS route_id -> canonical line (static routes.txt, agency "MTA NYCT").
_ROUTES: Final = {
    route: LineId(f"us:nyct_subway:{route.lower()}")
    for route in (
        "A", "C", "E", "B", "D", "F", "FX", "M", "G", "J", "Z", "L", "N", "Q", "R", "W",
        "GS", "FS", "H", "1", "2", "3", "4", "5", "6", "6X", "7", "7X", "SI",
    )
}
_PLANNED_WORK: Final = "lmm:planned_work"


def _unplanned(entity: FeedEntity) -> bool:
    if not entity.entity_id.startswith("lmm:"):
        raise ParseError(f"Undocumented MTA alert entity ID: {entity.entity_id}")
    return not entity.entity_id.startswith(_PLANNED_WORK)


_SCOPE: Final = FeedScope(
    routes=_ROUTES, agency_ids=frozenset(("MTASBWY",)), language="en", include=_unplanned,
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="MTA New York City Subway (GTFS-realtime alerts)",
    source_page_url=HttpUrl(_PAGE),
    endpoints=(
        SourceEndpoint(
            url=_FEED, method="GET", format=DataFormat.PROTOBUF,
            description="GTFS-realtime FeedMessage of subway alerts with Mercury extensions",
        ),
    ),
    terms_url=HttpUrl("https://www.mta.info/developers/terms-and-conditions"),
    additional_terms_urls=(
        HttpUrl("https://www.mta.info/document/90881"),
        HttpUrl("https://www.mta.info/doing-business-with-us/licensing-program"),
    ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "MTA's data feed terms (updated 2024-03-13) grant use under conditions: "
        "download and store the feed on a non-MTA server that users of your app "
        "access, and MTA prohibits an app that makes the data available to others "
        "directly from MTA servers; do not modify or delete any of the data; do not "
        "state or imply that the app is licensed or endorsed by MTA without an MTA "
        "license, or that the data is accurate, complete or timely; disclose that "
        "information may not be real time when it lags by more than 1 minute; review "
        "MTA's licensing requirements. Recorded as PERMISSION_REQUIRED because reuse "
        "is restricted, not because a key is needed. This provider is opt-in; "
        "excluding planned work and selecting English text are presentation choices "
        "whose compatibility with the no-modification clause is not confirmed by MTA."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:40:00+00:00"),
)


class MtaSubwayProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _PAGE

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = tuple(LINE_CATALOG[identifier].create_line(_ID, _PAGE) for identifier in _ROUTES.values())
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return lines_from_feed(decode_feed(response.content), self.lines, _SCOPE, self._now())

    @property
    def route_a(self) -> Line:
        return self._line("a")

    @property
    def route_c(self) -> Line:
        return self._line("c")

    @property
    def route_e(self) -> Line:
        return self._line("e")

    @property
    def route_b(self) -> Line:
        return self._line("b")

    @property
    def route_d(self) -> Line:
        return self._line("d")

    @property
    def route_f(self) -> Line:
        return self._line("f")

    @property
    def route_fx(self) -> Line:
        return self._line("fx")

    @property
    def route_m(self) -> Line:
        return self._line("m")

    @property
    def route_g(self) -> Line:
        return self._line("g")

    @property
    def route_j(self) -> Line:
        return self._line("j")

    @property
    def route_z(self) -> Line:
        return self._line("z")

    @property
    def route_l(self) -> Line:
        return self._line("l")

    @property
    def route_n(self) -> Line:
        return self._line("n")

    @property
    def route_q(self) -> Line:
        return self._line("q")

    @property
    def route_r(self) -> Line:
        return self._line("r")

    @property
    def route_w(self) -> Line:
        return self._line("w")

    @property
    def route_gs(self) -> Line:
        """42 St Shuttle (GTFS route GS, displayed as S)."""
        return self._line("gs")

    @property
    def route_fs(self) -> Line:
        """Franklin Avenue Shuttle (GTFS route FS, displayed as S)."""
        return self._line("fs")

    @property
    def route_h(self) -> Line:
        """Rockaway Park Shuttle (GTFS route H, displayed as S)."""
        return self._line("h")

    @property
    def route_1(self) -> Line:
        return self._line("1")

    @property
    def route_2(self) -> Line:
        return self._line("2")

    @property
    def route_3(self) -> Line:
        return self._line("3")

    @property
    def route_4(self) -> Line:
        return self._line("4")

    @property
    def route_5(self) -> Line:
        return self._line("5")

    @property
    def route_6(self) -> Line:
        return self._line("6")

    @property
    def route_6x(self) -> Line:
        return self._line("6x")

    @property
    def route_7(self) -> Line:
        return self._line("7")

    @property
    def route_7x(self) -> Line:
        return self._line("7x")

    @property
    def route_si(self) -> Line:
        """Staten Island Railway (GTFS route SI, displayed as SIR)."""
        return self._line("si")
