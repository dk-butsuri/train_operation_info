"""Yokohama Municipal Subway's official current-operation list.

Investigation: public HTML/JavaScript inspection and live official JSON, including
the separate history endpoint (not a Wayback incident capture). The page at
https://status.hamabus.city.yokohama.lg.jp/operation/list configures apiBaseUrl
as https://cms.yokohama-operation.cld.navitime.jp. Public /_nuxt/CoffiUX-.js
fetches /api/web/railroad/operations?lang=ja; /_nuxt/CqGW2eWD.js filters items
by line.id and displays its normal card when that route's list is empty.
/_nuxt/Bjix2mz5.js defines BLUELINE="1", GREENLINE="2". /_nuxt/CpZcISDq.js
translates common.normal-service as 平常運行. A live empty list verifies NORMAL.

The official /api/web/railroad/operations/history?lang=ja returned seven past
Blue Line notices with operationStatus={id:"2", name:"遅延", updateTime:...}.
The list view displays operationStatus.name directly, establishing this pair as
DELAYED. All other code/name pairs stay UNKNOWN, even if their prose mentions
suspension, recovery or future plans. Icons and hasDelayStatus do not classify
impact. No current nonempty response, suspension code, Green Line incident or
same-event recovery capture was verified. Incident/recovery/corruption tests
are synthetic; using history items to exercise the current parser is explicitly
a synthetic envelope, not evidence of a current incident.

Runtime reads only the current list. Each validated list record is retained as
JSON in alert.description, including sections, cause, maxDelayTime, period and
the dedicated status. Detail-only additionalInfo/replacementTrains, histories,
certificates, bus notices, positions, external links and news are not fetched.
No long-term discriminator was verified inside this list; mixed notices remain.
NORMAL concerns this list alone. timing=UNKNOWN and active periods=None: no
dedicated applicability mapping was established. now is a server clock, period
is the displayed notice period, and updateTime is not displayed by this view;
none is substituted for line.updated_at. Unknown line IDs, mismatching route
names, duplicate group IDs within a route and broken required fields fail atomically.

The footer links the city's general site policy, which restricts unauthorized
reuse on the main www site, but explicitly distinguishes subsites. No explicit
extension of that policy or reuse grant for this subsite/API was verified:
usage_permission=UNSPECIFIED. Exact URLs, UTC times, hashes and limitations:
tests/fixtures/YOKOHAMA_SUBWAY.md and yokohama_subway_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Final

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_URL: Final = "https://status.hamabus.city.yokohama.lg.jp/operation/list"
_FEED: Final = "https://cms.yokohama-operation.cld.navitime.jp/api/web/railroad/operations?lang=ja"
_ID: Final = ProviderId("yokohama_subway")
_ROUTES: Final = (
    ("1", "ブルーライン", LineId("jp:operator_702b41c21dfa:line_103dce814f8a")),
    ("2", "グリーンライン", LineId("jp:operator_702b41c21dfa:line_7332f720bd3d")),
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Yokohama Municipal Subway official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_FEED, method="GET", format=DataFormat.JSON,
        description="Current Japanese subway operation list; history and detail endpoints excluded",
    ),),
    terms_url=HttpUrl("https://www.city.yokohama.lg.jp/aboutweb/sitepolicy.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note=(
        "The subsite footer links the city site policy. That policy restricts "
        "unauthorized copying/reuse on www.city.yokohama.lg.jp and distinguishes "
        "subsites; its applicability to this subsite/API was not established. "
        "No subsite-specific reuse permission was verified. Numerical data and "
        "simple tables/graphs are excluded from copyright protection by the policy. "
        "NORMAL describes only absence of records in the current subway list."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:52:08+00:00"),
)

_Text = Annotated[str, Field(min_length=1)]


class _Input(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Route(_Input):
    id: _Text
    name: _Text


class _Status(_Input):
    id: _Text
    name: _Text
    updateTime: AwareDatetime


class _Period(_Input):
    begin: AwareDatetime
    # The public view explicitly permits a missing/null end.
    end: AwareDatetime | None = None


class _Notice(_Input):
    operationGroupId: Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{1,64}$")]
    line: _Route
    icon: _Text
    period: _Period
    sections: list[_Text]
    # The view conditionally displays these fields when truthy.
    cause: str | None = None
    maxDelayTime: str | None = None
    operationStatus: _Status
    hasDelayStatus: bool


class _Feed(_Input):
    now: AwareDatetime
    items: list[_Notice]


def _parse(payload: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    feed = _Feed.model_validate_json(payload)
    names = {key: name for key, name, _ in _ROUTES}
    groups: set[tuple[str, str]] = set()
    for notice in feed.items:
        if notice.line.id not in names or names[notice.line.id] != notice.line.name:
            raise ParseError("Unknown or mismatching Yokohama Subway route")
        group = (notice.line.id, notice.operationGroupId)
        if group in groups:
            raise ParseError("Duplicate Yokohama Subway operation group")
        groups.add(group)
        if notice.period.end is not None and notice.period.end < notice.period.begin:
            raise ParseError("Reversed Yokohama Subway notice period")
    result: list[Line] = []
    for (key, name, _), line in zip(_ROUTES, lines):
        notices = [notice for notice in feed.items if notice.line.id == key]
        states = tuple(
            LineStatus.DELAYED if (n.operationStatus.id, n.operationStatus.name) == ("2", "遅延")
            else LineStatus.UNKNOWN for n in notices
        )
        alerts = tuple(make_alert(
            line, state, f"{name} 運行情報", notice.model_dump_json(),
            alert_id=f"{_ID}:{line.line_id}:{notice.operationGroupId}",
        ) for notice, state in zip(notices, states))
        result.append(snapshot(
            line, combined_status(states),
            "\n".join(f"{n.operationStatus.id}: {n.operationStatus.name}" for n in notices)
            if notices else "平常運行",
            fetched_at, alerts=alerts, source_line_names=(name,),
        ))
    return tuple(result)


class YokohamaSubwayProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL) for _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def blue(self) -> Line:
        return self._line("line_103dce814f8a")

    @property
    def green(self) -> Line:
        return self._line("line_7332f720bd3d")
