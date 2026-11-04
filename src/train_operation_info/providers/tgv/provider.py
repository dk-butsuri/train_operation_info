"""SNCF open-data TGV service notices, joined by advertised train and operator.

Investigation: public official XML/metadata and live abnormal responses,
2026-11-04; no historical normal/recovery response was verified.
https://transport.data.gouv.fr/datasets/horaires-sncf documents the commercial
train-number join. Runtime sources are the NeTEx timetable and SIRI SX feed
listed below. NeTEx ServiceJourney.BrandingRef OUI/TGVOUIGO/LYR together with
RailSubmode=highSpeedRail identify the covered TGV services. TrainNumberRef
joins TrainNumber.ForAdvertisement; responsibilitySetRef joins the numeric
SIRI AffectedVehicleJourney.Operator.OperatorRef. No identifier substrings,
train-number ranges, route names or incident prose classify a service.

TER/IC/ICN/OUIGO_TC/DBS brands are outside the declared scope; SNF, new brands,
ambiguous joins and notices without a resolvable journey stay unclassified.
Notice Summary/Description/Detail (French), Progress and Severity are kept.
Severity slight also occurs on cancellation notices: it is not an effect code.
Individual-train notices cannot establish a whole-group delay or suspension:
network UNKNOWN with OTHER alerts and affected_line_ids=(). NORMAL means only
no published notice in scope and no unresolved notice, never all trains on time.
ResponseTimestamp is the feed's generation timestamp, not incident onset.
ValidityPeriod is a publication window; it does not establish impact bounds or
ACTIVE timing. Planned/long-duration work is mixed into the same publication
structure and retained; no prose/date filtering is used. Raw captures contain
the full feed, including excluded services. Timetable ServiceAlteration=planned
describes a scheduled journey and is not an incident category.

Each refresh downloads both complete inputs, so record/replay is self-contained.
The large timetable is parsed incrementally in a worker thread; opt-in only.
The passenger website refused the identifying User-Agent with HTTP 403 and is
never accessed or bypassed. Open-data feeds independently returned HTTP 200.
Evidence, retrieval times and hashes: tests/fixtures/TGV.md, tgv_manifest.json.
Empty/recovery, unknown-brand, malformed and refusal scenarios are synthetic.
"""

import asyncio
from collections.abc import Iterator
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Final
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_PAGE: Final = "https://transport.data.gouv.fr/datasets/horaires-sncf"
_TIMETABLE: Final = "https://eu.ftp.opendatasoft.com/sncf/plandata/export-opendata-sncf-netex.zip"
_ALERTS: Final = "https://proxy.transport.data.gouv.fr/resource/sncf-siri-lite-situation-exchange"
_N: Final = "{http://www.netex.org.uk/netex}"
_S: Final = "{http://www.siri.org.uk/siri}"
_LANG: Final = "{http://www.w3.org/XML/1998/namespace}lang"
_TGV: Final = frozenset({"OUI", "TGVOUIGO", "LYR"})
_EXCLUDED: Final = frozenset({"TER", "IC", "ICN", "OUIGO_TC", "DBS"})
_ID: Final = ProviderId("tgv")
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="SNCF open-data TGV service notices",
    source_page_url=HttpUrl(_PAGE),
    endpoints=(
        SourceEndpoint(url=_TIMETABLE, method="GET", format=DataFormat.XML,
                       description="ZIP-compressed NeTEx XML; advertised train/operator/brand join."),
        SourceEndpoint(url=_ALERTS, method="GET", format=DataFormat.XML,
                       description="Complete SIRI SX feed, filtered by NeTEx train brands."),
    ),
    terms_url=HttpUrl("https://data.sncf.com/pages/cgu/A1#A1"),
    additional_terms_urls=(HttpUrl("https://opendatacommons.org/licenses/odbl/1-0/"),),
    usage_permission=UsagePermission.COMMERCIAL_ALLOWED,
    usage_note=(
        "SNCF Voyageurs open data, licensed under ODbL 1.0 by the official dataset metadata. "
        "Reuse, including commercial use, is subject to attribution, licence notices and "
        "applicable share-alike obligations; individual content may carry additional rights. "
        "Covers published train-specific TGV INOUI, high-speed OUIGO and Lyria notices, "
        "not train punctuality, all network incidents or every international service. "
        "Explicit selection only: every refresh downloads the large national NeTEx archive."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:44:03.694488+00:00"),
)


def _one(element: ET.Element, path: str) -> ET.Element:
    found = element.findall(path)
    if len(found) != 1:
        raise ParseError(f"TGV required XML element missing or duplicated: {path}")
    return found[0]


def _text(element: ET.Element) -> str:
    if len(element) or element.text is None or not element.text.strip():
        raise ParseError("TGV required XML value empty or unexpectedly nested")
    return element.text.strip()


def _attribute(element: ET.Element, name: str) -> str:
    value = element.get(name)
    if value is None or not value.strip():
        raise ParseError(f"TGV required XML attribute missing: {name}")
    return value


def _records(data: bytes) -> Iterator[ET.Element]:
    """Retain one timetable record at a time, including its children only."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = [item for item in archive.infolist() if item.filename.endswith(".xml")]
            if len(members) != 1:
                raise ParseError("TGV timetable must contain exactly one XML document")
            with archive.open(members[0]) as stream:
                stack: list[ET.Element] = []
                protected: ET.Element | None = None
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    if event == "start":
                        if not stack and element.tag != _N + "PublicationDelivery":
                            raise ParseError("TGV timetable publication root changed")
                        stack.append(element)
                        if element.tag in (_N + "ServiceJourney", _N + "TrainNumber"):
                            if protected is not None:
                                raise ParseError("TGV timetable records unexpectedly nested")
                            protected = element
                        continue
                    if element is protected:
                        yield element
                        protected = None
                    if protected is None:
                        if len(stack) > 1:
                            stack[-2].remove(element)
                        element.clear()
                    stack.pop()
    except (BadZipFile, NotImplementedError, RuntimeError) as exc:
        raise ParseError("TGV timetable ZIP cannot be read") from exc


def _train_scope(data: bytes) -> dict[tuple[str, str], frozenset[bool | None]]:
    numbers: dict[str, tuple[str, str]] = {}
    journeys: list[tuple[str, str, bool | None]] = []
    identifiers: set[str] = set()
    observed_brands: set[str] = set()
    for element in _records(data):
        identifier = _attribute(element, "id")
        if identifier in identifiers:
            raise ParseError("TGV timetable record ID duplicated")
        identifiers.add(identifier)
        operator = _attribute(element, "responsibilitySetRef")
        if element.tag == _N + "TrainNumber":
            numbers[identifier] = (operator, _text(_one(element, _N + "ForAdvertisement")))
            continue
        brand = _attribute(_one(element, _N + "BrandingRef"), "ref")
        observed_brands.add(brand)
        submodes = element.findall(_N + "TransportSubmode/" + _N + "RailSubmode")
        if len(submodes) > 1:
            raise ParseError("TGV timetable rail submode duplicated")
        submode = _text(submodes[0]) if submodes else None
        scope: bool | None = None
        if brand in _TGV and submode == "highSpeedRail":
            scope = True
        elif brand in _EXCLUDED:
            scope = False
        references = element.findall(_N + "trainNumbers/" + _N + "TrainNumberRef")
        if not references:
            raise ParseError("TGV timetable journey has no train-number reference")
        for reference in references:
            journeys.append((operator, _attribute(reference, "ref"), scope))
    if not numbers or not journeys or not _TGV <= observed_brands:
        raise ParseError("TGV timetable empty or covered brands missing")
    scopes: dict[tuple[str, str], set[bool | None]] = {}
    for operator, number_reference, scope in journeys:
        number = numbers.get(number_reference)
        if number is None or number[0] != operator:
            raise ParseError("TGV timetable train-number/operator reference unresolved")
        scopes.setdefault(number, set()).add(scope)
    return {number: frozenset(values) for number, values in scopes.items()}


def _french(element: ET.Element, tag: str, *, required: bool = True) -> str:
    nodes = [node for node in element.findall(_S + tag) if node.get(_LANG) == "FR"]
    if len(nodes) > 1 or (required and not nodes):
        raise ParseError(f"TGV French {tag} missing or duplicated")
    return _text(nodes[0]) if nodes else ""


def _parse(
    data: bytes, scopes: dict[tuple[str, str], frozenset[bool | None]],
    line: Line, fetched_at: datetime,
) -> tuple[Line, ...]:
    root = ET.fromstring(data)
    if root.tag != _S + "Siri" or root.get("version") != "2.0":
        raise ParseError("TGV SIRI root/version changed")
    service = _one(root, _S + "ServiceDelivery")
    delivery = _one(service, _S + "SituationExchangeDelivery")
    for node in (service, delivery):
        if node.findall(_S + "ErrorCondition"):
            raise ParseError("TGV SIRI delivery reports an error")
        statuses = node.findall(_S + "Status")
        if len(statuses) > 1 or (statuses and _text(statuses[0]) not in ("true", "1")):
            raise ParseError("TGV SIRI delivery is unsuccessful")
    updated_at = datetime.fromisoformat(_text(_one(delivery, _S + "ResponseTimestamp")).replace("Z", "+00:00"))
    if updated_at.utcoffset() is None:
        raise ParseError("TGV SIRI timestamp is not timezone aware")
    situations = _one(delivery, _S + "Situations")
    if any(node.tag != _S + "PtSituationElement" for node in situations):
        raise ParseError("TGV SIRI situations structure changed")
    alerts: list[ServiceAlert] = []
    identifiers: set[str] = set()
    for notice in situations:
        identifier = _text(_one(notice, _S + "SituationNumber"))
        if identifier in identifiers:
            raise ParseError("TGV SIRI situation ID duplicated")
        identifiers.add(identifier)
        consequences = _one(notice, _S + "Consequences")
        journeys = consequences.findall(".//" + _S + "AffectedVehicleJourney")
        resolved: list[frozenset[bool | None]] = []
        train_labels: list[str] = []
        for journey in journeys:
            number = _text(_one(journey, _S + "VehicleJourneyRef"))
            operator = _text(_one(journey, _S + "Operator/" + _S + "OperatorRef"))
            resolved.append(scopes.get((operator, number), frozenset({None})))
            train_labels.append(f"{operator}:{number}")
        # Only an entirely proven out-of-scope target may be discarded.
        if resolved and all(value == frozenset({False}) for value in resolved):
            continue
        title = _french(notice, "Summary")
        description = _french(notice, "Description", required=False)
        detail = _french(notice, "Detail")
        progress = _text(_one(notice, _S + "Progress"))
        severity = _text(_one(notice, _S + "Severity"))
        # Preserve source HTML (including links), alongside the plain description.
        # There is no incident classification based on this text.
        body = "\n\n".join(part for part in (
            description, detail, "Trains: " + ", ".join(dict.fromkeys(train_labels))
            if train_labels else "", f"Progress: {progress}; Severity: {severity}",
        ) if part)
        if not BeautifulSoup(detail, "html.parser").get_text(strip=True):
            raise ParseError("TGV notice detail has no text")
        alerts.append(make_alert(
            line, LineStatus.ALERT, title, body, alert_id="tgv:" + identifier,
            affected_line_ids=(), language="fr",
        ))
    return (snapshot(
        line, LineStatus.UNKNOWN if alerts else LineStatus.NORMAL,
        "Published or unresolved train notices" if alerts else "No published notice in scope",
        fetched_at, updated_at=updated_at, alerts=tuple(alerts),
    ),)


class TgvProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE
    _metadata = _METADATA
    _timeout = 90.0

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__((
            LINE_CATALOG[LineId("fr:sncf:tgv")].create_line(_ID, _PAGE),
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        timetable = await self._get(client, _TIMETABLE)
        timetable.raise_for_status()
        scopes = await asyncio.to_thread(_train_scope, timetable.content)
        response = await self._get(client, _ALERTS)
        response.raise_for_status()
        return _parse(response.content, scopes, self.network, self._now())

    @property
    def network(self) -> Line:
        return self._line("tgv")
