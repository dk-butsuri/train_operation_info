"""Kaohsiung MRT/LRT's official, server-rendered operating-status panels.

Investigation: public HTML/JavaScript inspection and archived official HTML.
https://www.krtc.com.tw/ publishes #RtStatus and #RtStatusMobile, with
separate rows headed 捷運 and 輕軌. The MRT row covers red/orange together;
it does not identify individual affected routes. The green marker (g ci)
and exact labels 捷運全線正常營運 / 輕軌全線正常營運 are verified by live HTML
and https://web.archive.org/web/20261017100942id_/https://www.krtc.com.tw/.
The inline CSS defines g/r/y colours, but no disruption semantics. The inline
scripts and https://www.krtc.com.tw/scripts/common.js provide no additional
status mapping. Earlier inspected 2024/2025/July 2026 HTML lacks these panels.
No abnormal panel was obtained: delay/suspension/partial suspension, recovery
wording and active timing are unverified. All non-normal pairs stay UNKNOWN;
unknown/malformed/disagreement and recovery-transition tests are synthetic.

Both responsive panels must agree. Missing/duplicate/unidentifiable rows or
markers fail the entire refresh. Unknown labels/markers and linked references
are retained without interpreting prose. No source update time or incident
validity interval is published in these rows: updated_at/active_from/active_until
stay None, timing stays UNKNOWN and affected_line_ids stays empty. News,
planned works, linked article bodies, timetables and arrival times are outside
coverage; raw HTTP recordings still contain excluded homepage sections.
Provenance, hashes, terms and limitations: tests/fixtures/KAOHSIUNG_METRO.md
and kaohsiung_metro_manifest.json. Third-party response bodies stay local.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, LINE_CATALOG, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.krtc.com.tw/"
_ID: Final = ProviderId("kaohsiung_metro")
_ROWS: Final = {
    "捷運": (LineId("tw:krtc:metro"), "捷運全線正常營運"),
    "輕軌": (LineId("tw:krtc:light_rail"), "輕軌全線正常營運"),
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Kaohsiung Metro (MRT/LRT)",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="MRT red/orange group and light-rail operating panels (desktop/mobile)",
    ),),
    terms_url=HttpUrl("https://www.krtc.com.tw/WebService/privates"),
    additional_terms_urls=(HttpUrl("https://www.krtc.com.tw/WebService/security"),),
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note=(
        "The official homepage reserves copyright to Kaohsiung Rapid Transit "
        "Corporation. Its linked privacy and information-security policies "
        "were reviewed; no service-status reuse licence or affirmative "
        "commercial reuse grant was found. Public access does not establish "
        "permission to redistribute website content."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T13:06:59.864300+00:00"),
)


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels: list[dict[LineId, tuple[tuple[str, ...], str, tuple[str, ...]]]] = []
    for selector in ("#RtStatus", "#RtStatusMobile"):
        matches = soup.select(selector)
        if len(matches) != 1:
            raise ParseError("Kaohsiung Metro operating panel is missing or duplicated")
        rows = matches[0].select(":scope > div")
        if len(rows) != len(_ROWS):
            raise ParseError("Kaohsiung Metro operating rows are missing or duplicated")
        values: dict[LineId, tuple[tuple[str, ...], str, tuple[str, ...]]] = {}
        for row in rows:
            icons = row.select(":scope > .ci")
            if len(icons) != 1 or icons[0].get_text(strip=True):
                raise ParseError("Kaohsiung Metro operating marker is missing or changed")
            label = row.get_text(" ", strip=True)
            groups = [identifier for prefix, (identifier, _) in _ROWS.items() if label.startswith(prefix)]
            if len(groups) != 1 or groups[0] in values or label in _ROWS:
                raise ParseError("Kaohsiung Metro operating group is missing, unknown or duplicated")
            markers = tuple(sorted(icons[0].get_attribute_list("class")))
            row_references: list[str] = []
            for link in row.select("a[href]"):
                href = link.get("href")
                if not isinstance(href, str) or not href.strip():
                    raise ParseError("Kaohsiung Metro operating reference is empty")
                row_references.append(urljoin(_URL, href))
            values[groups[0]] = (markers, label, tuple(dict.fromkeys(row_references)))
        panels.append(values)
    if panels[0] != panels[1]:
        raise ParseError("Kaohsiung Metro desktop and mobile operating statuses disagree")
    expected = {identifier: label for identifier, label in _ROWS.values()}
    if panels[0].keys() != expected.keys():
        raise ParseError("Kaohsiung Metro operating group list is incomplete")
    result: list[Line] = []
    for line in lines:
        markers, label, references = panels[0][line.line_id]
        status = (
            LineStatus.NORMAL
            if markers == ("ci", "g") and label == expected[line.line_id] and not references
            else LineStatus.UNKNOWN
        )
        raw = label if status is LineStatus.NORMAL else f"{label} [{' '.join(markers)}]"
        alerts = () if status is LineStatus.NORMAL else (make_alert(
            line, status, f"{line.name}營運狀態", "\n".join((raw, *references)),
            affected_line_ids=(), language="zh-Hant",
        ),)
        result.append(snapshot(line, status, raw, fetched_at, alerts=alerts))
    return tuple(result)


class KaohsiungMetroProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            tuple(LINE_CATALOG[identifier].create_line(_ID, _URL) for identifier, _ in _ROWS.values()),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content.decode("utf-8"), self.lines, self._now())

    @property
    def metro(self) -> Line:
        return self._line("metro")

    @property
    def light_rail(self) -> Line:
        return self._line("light_rail")
