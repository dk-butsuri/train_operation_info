"""Hakone Navi's official Hakone Tozan Railway notice (Odawara--Gora).

Investigation: public HTML/JavaScript and archived official HTML.
https://www.hakonenavi.jp/transportation/ renders .operation_item server-side.
T0001 / RT0004 / 箱根登山電車 identify the railway; T0002 is the separate
cable car. The linked /hakone-tozan/ page lists Odawara--Gora stations.
https://www.hakonenavi.jp/assets/js/script.js?v=1784599900 only toggles
.operation_item_toggle; /_include/json_operation.php is a whole-area summary,
not railway status. Neither that summary nor other modes are consumed.

Wayback https://web.archive.org/web/{timestamp}id_/ followed by
https://www.hakonenavi.jp/transportation/ was inspected at 20230326061457,
20250321040309 and 20260208142500: the railway is normal while other modes
can have warnings. The latter two verify operation_item-error /
operation_state-error as generic warnings, with structured section details.
They do not prove total railway suspension. Earlier 20191019095417,
20191118050015, 20191214011408, 20200401233055 and 20200716163557 use a
different legacy layout: railway suspension heading can coexist with a
closure of only Hakone-Yumoto--Gora. They are investigation evidence only;
the legacy layout is deliberately not parsed. The modern railway abnormal
layout, delay labels and same-event recovery remain unverified.

Exact normal status with no extra notice maps to NORMAL. Verified generic
error styling maps to ALERT (not a particular disruption). Unrecognized
labels/styles and normal with additional notice remain UNKNOWN with text.
No prose keywords determine DELAYED/SUSPENDED/PARTIAL_SUSPENSION or timing.
Business-hours completion/advance plans remain UNKNOWN, never NO_SERVICE.
Warning/detail tests for T0001 are explicitly synthetic, based on other
modes' verified common markup, not claimed as real railway incidents.

No dedicated update/applicability fields were verified: updated_at=None,
timing=UNKNOWN and active periods unset. data-debug is page generation time.
Only the T0001 item including captions/sections is consumed. Separate news,
global advisories, linked articles, congestion, cable car, ropeway, boats,
buses, positions and certificates are outside scope. Long-term notices
within the item are retained without duration inference; separate planned
changes are not fetched. Evidence/hashes: tests/fixtures/HAKONE_TOZAN.md and
hakone_tozan_manifest.json. Malformed HTML fails atomically.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.hakonenavi.jp/transportation/"
_ID: Final = ProviderId("hakone_tozan")
_LINE_ID: Final = LineId("jp:operator_5dbad158fdda:line_a0694844624f")
_NORMAL: Final = "平常通り運行中"
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Hakone Tozan official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Server-rendered Japanese T0001 railway status and details only",
    ),),
    terms_url=HttpUrl("https://www.hakonenavi.jp/policy/"),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "Site policy sections 2 and 4 restrict unauthorized reproduction/modification "
        "of site content, reserving statutory private use and quotation; quotations "
        "require attribution. No commercial reuse grant was found. Only the railway "
        "item is parsed; separate news, global advisories and other transport modes "
        "are outside the parsed scope, though present in the recorded HTTP body."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-02T15:51:55.396318+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    found = parent.select(selector)
    if len(found) != 1:
        raise ParseError(f"Hakone Tozan element missing or duplicated: {selector}")
    return found[0]


def _parse(html: bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    operation = _one(soup, '.operation_contents[data-toggle-contents="operation"]')
    item = _one(operation, '.operation_item[data-code="T0001"]')
    if item.get("data-name") != "箱根登山電車" or item.get("data-route-cd") != "RT0004":
        raise ParseError("Hakone Tozan railway identity changed")
    for hidden in item.select("script, style, template, noscript"):
        hidden.decompose()
    state = _one(item, ".operation_stateWrap > .operation_state")
    label = state.get_text(" ", strip=True)
    if not label or label == "-":
        raise ParseError("Hakone Tozan status is empty")
    # Preserve all textual details rather than only recognized section fields.
    body = item.get_text("\n", strip=True)
    item_classes = set(item.get_attribute_list("class"))
    state_classes = set(state.get_attribute_list("class"))
    known_item = {"operation_item", "operation_item-error"}
    known_state = {"operation_state", "operation_state-error"}
    item_warning = "operation_item-error" in item_classes
    state_warning = "operation_state-error" in state_classes
    if (item_classes - known_item or state_classes - known_state
            or item_warning != state_warning):
        status = LineStatus.UNKNOWN
    elif item_warning:
        # Verified warning styling has no full-line closure semantics.
        status = LineStatus.UNKNOWN if label == _NORMAL else LineStatus.ALERT
    elif label == _NORMAL and body == _NORMAL:
        status = LineStatus.NORMAL
    else:
        status = LineStatus.UNKNOWN
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, label, body),
    )
    return (snapshot(
        line, status, label, fetched_at, alerts=alerts,
        source_line_names=("箱根登山電車",),
    ),)


class HakoneTozanProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE_ID].create_line(_ID, _URL),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
