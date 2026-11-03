"""DB Verkehrslage: the official DB_Fernverkehr organisational listing.

Investigation: public HTML/JavaScript reverse engineering and live abnormal
JSON responses, 2026-11-03 UTC; no Wayback abnormal capture was used.
https://www.bahn.de/service/fahrplaene/aktuell now redirects to Verkehrslage.
https://verkehrslage.bahnhof.de/de/region/DB_Fernverkehr embeds the public
Nuxt configuration used by /_nuxt/CVs5M6ee.js. Its risApi client sends the
public risApiKey to same-origin /api requests. /_nuxt/Dhqahhbt.js calls
/api/views/disruptions with channels=AwarenessBlitzbox,TrafficReport,
organisationalUnitNames=DB_Fernverkehr, Berlin-local date bounds, limit and
offset. The returned total is a pagination bound, not the exact number of
objects: the saved response has total=72 and 70 communications. All pages
are fetched atomically. SSR's initial zero count is NOT an empty-list signal.

The official construction/disruption selector in /_nuxt/CVs5M6ee.js tests
disruption.cause == CONSTRUCTION; those entries are excluded from output.
Other causes, including unknown future causes, are preserved. Parent and
child communications are retained individually rather than dropping details.
/api/views/message?id={id}&locale=DE supplies caption, summary, communication.
HTML communication is converted to text, retaining paragraph boundaries.

The listing identifies an organisational scope, not a canonical affected
line. The group stays UNKNOWN when notices exist; each notice is OTHER with
affected_line_ids=(). NO_SERVICE, IMPAIRMENT etc. are not interpreted as
network-wide suspension or delay. No prose classification is performed.
An empty complete filtered listing means NORMAL only within this listing's
scope for the current Berlin-local date, not proof of punctuality or the
absence of DB Regio, S-Bahn, construction, or train-specific problems.

Communication end and disruption.end are dedicated expiry fields used by
the official frontend; expired communications are omitted. The frontend's
As() also excludes a child when its immediate parent is missing or expired.
Parent identities and expiry fields are retained for that same filter.
Applicability is
otherwise UNKNOWN, including future and recurring notices. No incident
validity or update timestamp is fabricated from publication/communication
dates: active_from/active_until and updated_at remain None. Construction
entries remain in recorded HTTP responses. Fixtures, transformation details,
source hashes, permission restrictions and unverified cases: DB.md and
db_manifest.json under tests/fixtures/. Empty, malformed, recovery and
pagination cases are synthetic, not archived evidence of source behaviour.
"""

from datetime import datetime, time, timedelta
import json
from pathlib import Path
import re
from typing import Final
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, JsonValue

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_BASE: Final = "https://verkehrslage.bahnhof.de"
_URL: Final = _BASE + "/de/region/DB_Fernverkehr"
_ID: Final = ProviderId("db")
_LINE_ID: Final = LineId("de:db_fernverkehr:network")
_LIMIT: Final = 100
_ZONE: Final = ZoneInfo("Europe/Berlin")
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="DB Verkehrslage (Fernverkehr)",
    source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_URL, method="GET", format=DataFormat.HTML,
                       description="Public Nuxt configuration for the same-origin web API"),
        SourceEndpoint(
            url=_BASE + "/api/views/disruptions?channels=AwarenessBlitzbox%2CTrafficReport"
            "&organisationalUnitNames=DB_Fernverkehr&from={from_date}&to={to_date}"
            "&limit=100&offset={offset}",
            method="GET", format=DataFormat.JSON, is_template=True,
            description="Berlin-local current-day listing; all pages, with public x-api-key from HTML",
        ),
        SourceEndpoint(
            url=_BASE + "/api/views/message?id={communication_id}&locale=DE",
            method="GET", format=DataFormat.JSON, is_template=True,
            description="German detail text for each non-construction, non-expired communication",
        ),
    ),
    terms_url=HttpUrl(_BASE + "/de/impressum"),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "DB InfraGO's Verkehrslage terms reserve rights, permit display/checking "
        "information and functions provided on the website, and require prior "
        "written consent for other uses. Commercial copying, processing and "
        "republication, including automated extraction, require prior written "
        "consent. This public website API is not an open-data reuse licence. "
        "Scope: DB_Fernverkehr traffic-report channels for the current Berlin "
        "date, excluding the dedicated CONSTRUCTION category; DB Regio and "
        "S-Bahn listings and construction notices are outside this provider."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:37:51.151658+00:00"),
)


class _Source(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Unit(_Source):
    name: str = Field(min_length=1)


class _Hints(_Source):
    channels: list[str]
    organisationalUnits: list[_Unit]


class _Disruption(_Source):
    cause: str = Field(min_length=1)
    end: AwareDatetime | None = None


class _Header(_Source):
    # Keep unused JSON for the second, in-scope validation pass. Construction
    # notices need only the common identity, parent and expiry/cause envelope.
    model_config = ConfigDict(strict=True, extra="allow")
    __pydantic_extra__: dict[str, JsonValue] = Field(init=False)
    disruptionCommunicationID: str = Field(min_length=1)
    disruption: _Disruption
    end: AwareDatetime | None = None
    parent: str | None = Field(default=None, min_length=1)


class _Communication(_Header):
    model_config = ConfigDict(strict=True, extra="ignore")
    consumerHints: _Hints
    effect: str = Field(min_length=1)


class _Page(_Source):
    disruptionCommunications: list[_Header]
    offset: int = Field(ge=0)
    limit: int = Field(gt=0)
    total: int = Field(ge=0)


class _Message(_Source):
    caption: str = Field(min_length=1)
    summary: str
    communication: str


def _public_key(html: bytes) -> str:
    soup = BeautifulSoup(html, "html.parser")
    scripts = [s.get_text() for s in soup.select("script")
               if "window.__NUXT__.config=" in s.get_text()]
    if len(scripts) != 1:
        raise ParseError("DB public Nuxt configuration missing or duplicated")
    keys = re.findall(r'risApiKey:("(?:\\.|[^"\\])*")', scripts[0])
    origins = re.findall(r'risApiUrl:("(?:\\.|[^"\\])*")', scripts[0])
    if len(keys) != 1 or len(origins) != 1 or json.loads(origins[0]) != _BASE:
        raise ParseError("DB public API configuration changed")
    key: str = json.loads(keys[0])
    if not key or not key.isascii() or any(ord(c) < 33 or ord(c) == 127 for c in key):
        raise ParseError("DB public API key missing or invalid")
    return key


def _detail_text(message: _Message) -> str:
    body = BeautifulSoup(message.communication, "html.parser")
    for tag in body.select("script, style, template, noscript"):
        tag.decompose()
    return "\n".join(part for part in (message.summary.strip(), body.get_text("\n", strip=True)) if part)


class DbProvider(SnapshotProvider):
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
        page_response = await self._get(client, _URL)
        page_response.raise_for_status()
        headers = {"x-api-key": _public_key(page_response.content)}
        now = self._now()
        local = now.astimezone(_ZONE)
        start = datetime.combine(local.date(), time.min, _ZONE)
        end = datetime.combine(local.date() + timedelta(days=1), time.min, _ZONE) - timedelta(milliseconds=1)
        entries: list[_Header] = []
        total: int | None = None
        offset = 0
        while total is None or offset < total:
            params = urlencode({
                "channels": "AwarenessBlitzbox,TrafficReport",
                "organisationalUnitNames": "DB_Fernverkehr",
                "from": start.isoformat(timespec="milliseconds"),
                "to": end.isoformat(timespec="milliseconds"),
                "limit": _LIMIT, "offset": offset,
            })
            response = await self._get(client, _BASE + "/api/views/disruptions?" + params, headers=headers)
            response.raise_for_status()
            page = _Page.model_validate_json(response.content)
            if page.offset != offset or page.limit != _LIMIT or len(page.disruptionCommunications) > _LIMIT:
                raise ParseError("DB pagination response does not match request")
            if total is not None and page.total != total:
                raise ParseError("DB listing changed during pagination")
            total = page.total
            if not total and page.disruptionCommunications:
                raise ParseError("DB nonempty listing has zero total")
            entries.extend(page.disruptionCommunications)
            offset += _LIMIT

        by_id = {entry.disruptionCommunicationID: entry for entry in entries}
        if len(by_id) != len(entries):
            raise ParseError("DB duplicate communication across listing pages")

        def expired(entry: _Header) -> bool:
            return any(end_at is not None and end_at < now for end_at in (entry.end, entry.disruption.end))

        alerts: list[ServiceAlert] = []
        source_states: list[str] = []
        for header in entries:
            if header.disruption.cause == "CONSTRUCTION":
                continue
            if expired(header):
                continue
            if header.parent is not None:
                parent = by_id.get(header.parent)
                if parent is None or expired(parent):
                    continue
            entry = _Communication.model_validate_json(header.model_dump_json())
            identifier = entry.disruptionCommunicationID
            if "DB_Fernverkehr" not in [u.name for u in entry.consumerHints.organisationalUnits]:
                raise ParseError("DB organisational-unit filter not applied")
            if not set(entry.consumerHints.channels).intersection(("AwarenessBlitzbox", "TrafficReport")):
                raise ParseError("DB channel filter not applied")
            response = await self._get(
                client, _BASE + "/api/views/message?" + urlencode({"id": identifier, "locale": "DE"}),
                headers=headers,
            )
            response.raise_for_status()
            message = _Message.model_validate_json(response.content)
            description = _detail_text(message)
            if not message.caption.strip() or not description:
                raise ParseError("DB communication has no title or body")
            alerts.append(make_alert(
                self.fernverkehr, LineStatus.ALERT, message.caption, description,
                alert_id="db:" + identifier, affected_line_ids=(), language="de",
            ))
            source_states.append(entry.effect)
        state = LineStatus.UNKNOWN if alerts else LineStatus.NORMAL
        return (snapshot(
            self.fernverkehr, state, "\n".join(source_states) if alerts else "",
            now, alerts=tuple(alerts),
        ),)

    @property
    def fernverkehr(self) -> Line:
        return self.lines[0]
