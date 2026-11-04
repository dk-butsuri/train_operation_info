"""Metro-North Railroad: official keyless GTFS-realtime Service Alerts.

Investigation: official documentation, public JavaScript and a live protobuf
response, retrieved 2026-11-04 UTC; no archive. https://api.mta.info/ publishes
the camsys%2Fmnr-alerts URL in /static/js/main.bc5d42b5.js. This is the alerts
feed, not mnr%2Fgtfs-mnr (train movements, outside this library's scope).

MTA GTFS Alerts Feed Documentation (December 2021),
https://www.mta.info/document/90881, documents agency_id MNR and the
lmm:planned_work / lmm:alert distinction. Planned work is excluded by ID
before route validation, including unsupported IDs in that excluded scope.
Mercury alert_type is free text and is never classified. effect is documented
as unused and absent in the capture: kept alerts have UNKNOWN effect, line
status and timing. active_period is a display window, not an incident period;
it does not set active_from/active_until. Explicit effects follow the existing
shared GTFS-rt conversion; no prose or train delay duration is interpreted.

Route IDs 1-6 and names were verified against routes.txt in the official
https://rrgtfsfeeds.s3.amazonaws.com/gtfsmnr.zip. The official homepage's
https://consist.mta.info/vuejs/apps/common/index.min.js loads
https://otp-mta-prod.camsys-apps.com/otp/routers/default/index/routes
(verified accessible without a key), whose MNR records also define
50 = Pascack Valley and 51 = Port Jervis. These west-of-Hudson services are
absent from MNR static GTFS (MTA directs schedule users to NJ Transit).
The same script adds MNR:Wassaic as a separate subline and matches alert
route IDs case-insensitively; the capture uses "wassaic". Both source
spellings are registered explicitly. Wassaic is kept separate from Harlem;
branch or train alerts are not propagated to a parent line. Metro-North is
the service agency; NJ Transit operates the west-of-Hudson services under
contract. No existing canonical lines cover these nine publication units.

The live capture has ten entities: nine planned and one Harlem train delay,
with both route and trip selectors. Its source timestamp is retained.
Recovery, empty feeds, west/branch/Wassaic unplanned alerts, stop-only scope,
explicit effects and failures are synthetic tests; real recovery unverified.
Evidence, retrieval times, transformations and hashes:
tests/fixtures/METRO_NORTH.md and metro_north_manifest.json.
MTA's feed terms require explicit opt-in, as for mta_subway.
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

_PAGE: Final = "https://www.mta.info/"
_FEED: Final = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fmnr-alerts"
_ID: Final = ProviderId("metro_north")
_ROUTES: Final = {
    route: LineId(f"us:metro_north:{suffix}")
    for route, suffix in (
        ("1", "hudson"), ("2", "harlem"), ("3", "new_haven"),
        ("4", "new_canaan"), ("5", "danbury"), ("6", "waterbury"),
        ("50", "pascack_valley"), ("51", "port_jervis"),
        ("wassaic", "wassaic"), ("Wassaic", "wassaic"),
    )
}


def _unplanned(entity: FeedEntity) -> bool:
    if not entity.entity_id.startswith("lmm:"):
        raise ParseError(f"Undocumented MTA alert entity ID: {entity.entity_id}")
    return not entity.entity_id.startswith("lmm:planned_work")


_SCOPE: Final = FeedScope(
    routes=_ROUTES, agency_ids=frozenset(("MNR",)), language="en", include=_unplanned,
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Metro-North Railroad (GTFS-realtime alerts)",
    source_page_url=HttpUrl(_PAGE),
    endpoints=(SourceEndpoint(
        url=_FEED, method="GET", format=DataFormat.PROTOBUF,
        description="GTFS-realtime Metro-North Service Alerts with Mercury extensions",
    ),),
    terms_url=HttpUrl("https://www.mta.info/developers/terms-and-conditions"),
    additional_terms_urls=(
        HttpUrl("https://www.mta.info/document/90881"),
        HttpUrl("https://www.mta.info/doing-business-with-us/licensing-program"),
    ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "MTA's data feed terms (updated 2024-03-13) require downloading and "
        "storing the feed on a non-MTA server accessed by your app's users; "
        "an app may not make data available to others directly from MTA servers. "
        "Do not modify or delete data, imply MTA licensing or endorsement without "
        "a license, or claim accuracy, completeness or timeliness. Disclose lag "
        "over 1 minute and review MTA's licensing requirements. "
        "PERMISSION_REQUIRED records restricted reuse, not an API key requirement. "
        "Explicit opt-in only. Compatibility of excluding planned work and "
        "selecting English with the no-modification clause is not confirmed by MTA."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:00:00+00:00"),
)


class MetroNorthProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _PAGE

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = tuple(
            LINE_CATALOG[identifier].create_line(_ID, _PAGE)
            for identifier in dict.fromkeys(_ROUTES.values())
        )
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return lines_from_feed(decode_feed(response.content), self.lines, _SCOPE, self._now())

    @property
    def hudson(self) -> Line:
        return self._line("hudson")

    @property
    def harlem(self) -> Line:
        return self._line("harlem")

    @property
    def new_haven(self) -> Line:
        return self._line("new_haven")

    @property
    def new_canaan(self) -> Line:
        return self._line("new_canaan")

    @property
    def danbury(self) -> Line:
        return self._line("danbury")

    @property
    def waterbury(self) -> Line:
        return self._line("waterbury")

    @property
    def pascack_valley(self) -> Line:
        return self._line("pascack_valley")

    @property
    def port_jervis(self) -> Line:
        return self._line("port_jervis")

    @property
    def wassaic(self) -> Line:
        """The separately published Wassaic subline, not the whole Harlem line."""
        return self._line("wassaic")
