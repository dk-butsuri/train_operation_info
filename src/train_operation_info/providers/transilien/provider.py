"""SNCF Transilien's public traffic API, restricted to SNCF-operated lines.

Investigation: public HTML/JavaScript inspection and live abnormal JSON; no
archived abnormal response was used. https://www.transilien.com/fr/ mounts
component-traffic-info.bundle.js (version 52612). That official bundle fetches
https://www.transilien.com/api/traffic/infos and
https://www.transilien.com/api/traffic/line/{code}?lang=fr. Its currentDisruptions
and future/weekly/monthly lists are separate; missing current data are displayed
as unavailable (MISSING_CURRENT), never as an empty normal list. Require FULL
summary retrieval before accepting a complete snapshot.

Only RER C/D/E and train H/J/K/L/N/P/R/U/V are included. A/B's shared SNCF/RATP
operation and all trams/metro/buses are outside this provider's scope. Route
groups encompass their branches; a disruption identifies the group, not every
branch or station. currentDisruptions entries classified TRAVAUX are excluded
structurally, alongside the separate future lists. TRAFIC entries remain even
when their prose describes months of reduced service, as the RER D live sample
does. NORMAL means no included current traffic notice, not no engineering work.

The bundle maps SLOWED_TRAFFIC/HIGHLY_SLOWED_TRAFFIC to explicit slowed-traffic
labels. These become DELAYED. DISRUPTED_TRAFFIC, INTERRUPTED_TRAFFIC, NOT_SERVED_
STOP(S), HIGH_AFFLUENCE and the observed literal UNKNOWN preserve notices as
ALERT: interruption extent/full-line suspension is not established. New codes
or categories remain UNKNOWN with original text. Category TRAFIC and literal
UNKNOWN in live JSON establish an alert's existence but not its effect.
Current-list membership is a display grouping, not proof of actual incident
validity, so timing stays UNKNOWN. modifiedDate is an update timestamp;
broadcastStartDate is publication, never active_from. No incident periods are
inferred. Normal recovery, unknown codes and malformed JSON tests are synthetic.
Evidence, hashes, retrieval times and terms: tests/fixtures/TRANSILIEN.md and
transilien_manifest.json. Nationwide TGV/TER/Intercites are not covered.
"""

from datetime import datetime
from pathlib import Path
from typing import Final, Literal

import httpx
from bs4 import BeautifulSoup
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_ID: Final = ProviderId("transilien")
_URL: Final = "https://www.transilien.com/fr/#traffic-info-app"
_SUMMARY: Final = "https://www.transilien.com/api/traffic/infos"
_DETAIL: Final = "https://www.transilien.com/api/traffic/line/{code}?lang=fr"
_LINES: Final = (
    ("rer_c", "RER_C", "RER"), ("rer_d", "RER_D", "RER"),
    ("rer_e", "RER_E", "RER"), ("ligne_h", "LIGNE_H", "TRAIN"),
    ("ligne_j", "LIGNE_J", "TRAIN"), ("ligne_k", "LIGNE_K", "TRAIN"),
    ("ligne_l", "LIGNE_L", "TRAIN"), ("ligne_n", "LIGNE_N", "TRAIN"),
    ("ligne_p", "LIGNE_P", "TRAIN"), ("ligne_r", "LIGNE_R", "TRAIN"),
    ("ligne_u", "LIGNE_U", "TRAIN"), ("ligne_v", "LIGNE_V", "TRAIN"),
)
_STATES: Final = {
    "SLOWED_TRAFFIC": LineStatus.DELAYED,
    "HIGHLY_SLOWED_TRAFFIC": LineStatus.DELAYED,
    "DISRUPTED_TRAFFIC": LineStatus.ALERT,
    "INTERRUPTED_TRAFFIC": LineStatus.ALERT,
    "NOT_SERVED_STOP": LineStatus.ALERT,
    "NOT_SERVED_STOPS": LineStatus.ALERT,
    "HIGH_AFFLUENCE": LineStatus.ALERT,
    "UNKNOWN": LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="SNCF Transilien (12 SNCF-operated route groups)",
    source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_SUMMARY, method="GET", format=DataFormat.JSON,
                       description="FULL retrieval status for each supported route group"),
        SourceEndpoint(url=_DETAIL, method="GET", format=DataFormat.JSON,
                       is_template=True, description=(
                           "code is RER_C/D/E or LIGNE_H/J/K/L/N/P/R/U/V; "
                           "currentDisruptions only, excluding category TRAVAUX"
                       )),
    ),
    terms_url=HttpUrl("https://www.transilien.com/fr/page-editoriale/conditions-generales-dutilisation"),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "Official intellectual-property terms reserve all website use rights and "
        "require prior express permission for reproduction or representation. "
        "No separate reuse grant was found for the public traffic API. "
        "This provider covers only SNCF Transilien RER C/D/E and trains H/J/K/L/N/P/R/U/V, "
        "not nationwide SNCF, RER A/B or other operators."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:38:01.234788+00:00"),
)


class _Entry(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    code: str
    id: str
    mode: str
    fetchStatus: str


class _Summary(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    allPerturbationsByLine: list[_Entry]


class _Disruption(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    id: str = Field(min_length=1)
    modifiedDate: AwareDatetime
    category: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class _Works(BaseModel):
    """Only the discriminator belongs to the selected scope; works are ignored."""

    model_config = ConfigDict(strict=True, extra="ignore")
    category: Literal["TRAVAUX"]


class _Current(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    currentDisruptions: list[_Works | _Disruption]


def _description(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text("\n", strip=True)
    if not text:
        raise ParseError("Transilien notice has no visible description")
    links = tuple(dict.fromkeys(
        href for anchor in soup.select("a[href]")
        if isinstance(href := anchor.get("href"), str) and href.strip()
    ))
    return "\n".join((text, *links))


def _parse(payload: bytes, line: Line, fetched_at: datetime) -> Line:
    data = _Current.model_validate_json(payload)
    notices = [notice for notice in data.currentDisruptions
               if isinstance(notice, _Disruption) and notice.category != "TRAVAUX"]
    if len({notice.id for notice in notices}) != len(notices):
        raise ParseError("Transilien current notice ID is duplicated")
    alerts: list[ServiceAlert] = []
    states: list[LineStatus] = []
    labels: list[str] = []
    dates: list[datetime] = []
    for notice in notices:
        state = (
            _STATES.get(notice.severity, LineStatus.UNKNOWN)
            if notice.category == "TRAFIC" else LineStatus.UNKNOWN
        )
        states.append(state)
        labels.append(f"{notice.category}:{notice.severity}")
        dates.append(notice.modifiedDate)
        alerts.append(make_alert(
            line, state, notice.title, _description(notice.detail),
            alert_id=f"transilien:{line.line_id}:{notice.id}", language="fr",
        ))
    return snapshot(
        line, combined_status(tuple(states)),
        " | ".join(dict.fromkeys(labels)) if labels else "currentDisruptions: no traffic notices (TRAVAUX excluded)",
        fetched_at, updated_at=max(dates) if dates else None, alerts=tuple(alerts),
    )


class TransilienProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[LineId(f"fr:sncf:{key}")].create_line(_ID, _URL)
            for key, _, _ in _LINES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _SUMMARY)
        response.raise_for_status()
        summary = _Summary.model_validate_json(response.content)
        for _, code, mode in _LINES:
            entries = [entry for entry in summary.allPerturbationsByLine if entry.code == code]
            if len(entries) != 1 or entries[0].id != code or entries[0].mode != mode:
                raise ParseError(f"Transilien route identity is missing or ambiguous: {code}")
            if entries[0].fetchStatus != "FULL":
                raise ParseError(f"Transilien route retrieval is incomplete: {code}")
        fetched_at = self._now()
        lines: list[Line] = []
        for key, code, _ in _LINES:
            response = await self._get(client, _DETAIL.format(code=code))
            response.raise_for_status()
            lines.append(_parse(response.content, self._line(key), fetched_at))
        return tuple(lines)

    @property
    def rer_c(self) -> Line:
        return self._line("rer_c")

    @property
    def rer_d(self) -> Line:
        return self._line("rer_d")

    @property
    def rer_e(self) -> Line:
        return self._line("rer_e")

    @property
    def ligne_h(self) -> Line:
        return self._line("ligne_h")

    @property
    def ligne_j(self) -> Line:
        return self._line("ligne_j")

    @property
    def ligne_k(self) -> Line:
        return self._line("ligne_k")

    @property
    def ligne_l(self) -> Line:
        return self._line("ligne_l")

    @property
    def ligne_n(self) -> Line:
        return self._line("ligne_n")

    @property
    def ligne_p(self) -> Line:
        return self._line("ligne_p")

    @property
    def ligne_r(self) -> Line:
        return self._line("ligne_r")

    @property
    def ligne_u(self) -> Line:
        return self._line("ligne_u")

    @property
    def ligne_v(self) -> Line:
        return self._line("ligne_v")
