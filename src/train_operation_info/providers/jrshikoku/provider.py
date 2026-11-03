"""JR Shikoku official notices: archive and public HTML/CSS investigation.

Sources: https://www.jr-shikoku.co.jp/info/index.html and info/css/style.css.
Wayback 20250216210138 verifies Seto-Ohashi cancellations; 20260712052626
verifies Yodo partial suspension; 20240621132151 and 20260116145742 verify
weather and planned-work advisories. Replay URLs, hashes and extraction are
recorded in tests/fixtures/JRSHIKOKU.md and jrshikoku_manifest.json.
The live normal page verifies ten map sections. The summary combines delay
and suspension, and overlays only identify affected sections: incidents are
ALERT, never classified from narrative keywords. Named routes are narrowed
by active map sections; unnamed notices retain affected_line_ids=(). Unknown
summaries/headings/styles retain UNKNOWN and original text. Missing or
contradictory structure raises ParseError and preserves the previous snapshot.
Pure-delay and same-incident recovery archives are unverified. A later normal
page tests clearing; unknown/malformed cases are synthetic. Notice times are
Japan local time; normal has no source timestamp. Train positions, certificates,
linked PDFs and static attention-area notices are outside this provider's scope.
Mixed long-term notices are retained. Duration and applicability remain UNKNOWN;
notice prose is not classified. See fixtures/ALERT_CLASSIFICATION.md.
"""

from datetime import datetime
import re
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Comment, Tag
from pathlib import Path

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.jr-shikoku.co.jp/info/index.html"
_ID: Final = ProviderId("jrshikoku")
_ROUTES: Final = {
    "seto": LineId("jp:jr_shikoku:line_e0e7a7ecebce"),
    "yosan1": LineId("jp:jr_shikoku:line_5c01e50604fa"),
    "yosan2": LineId("jp:jr_shikoku:line_33d69f3cb472"),
    "dosan1": LineId("jp:jr_shikoku:line_53f79739e96a"),
    "dosan2": LineId("jp:jr_shikoku:line_55f63f4ebffa"),
    "kotoku": LineId("jp:jr_shikoku:line_71d4292395b3"),
    "mugi": LineId("jp:jr_shikoku:line_d5da40ac8c32"),
    "tokushima": LineId("jp:jr_shikoku:line_85cc278aea6c"),
    "naruto": LineId("jp:jr_shikoku:line_06ed0930edd2"),
    "yodo": LineId("jp:jr_shikoku:line_d43dbbda1b8c"),
}
_HEADINGS: Final = {
    "瀬戸大橋線": ("seto",), "予讃線": ("yosan1", "yosan2"),
    "土讃線": ("dosan1", "dosan2"), "高徳線": ("kotoku",),
    "牟岐線": ("mugi",), "徳島線": ("tokushima",),
    "鳴門線": ("naruto",), "予土線": ("yodo",),
}
_NORMAL: Final = "現在、遅れ等の情報はありません。"
_SUMMARIES: Final = {
    _NORMAL: {"nodelay"},
    "運行に関する情報があります。": {"nodelay", "delayactive"},
    "遅れまたは運転を見合わせている区間があります。": {"delay", "delayactive"},
}
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Route map and service notices',
        ),
    ),
    provider_id=_ID, name="JR Shikoku official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.jr-shikoku.co.jp/site_policy/index.shtm"),
    additional_terms_urls=(HttpUrl("https://www.jr-shikoku.co.jp/site_policy/jrshikoku_sitepolicy.pdf"), HttpUrl(_URL)),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="Site policy section 1 prohibits unapproved copying, transcription, distribution, translation and modification. Service notices cover delays of roughly 30 minutes or more and cancellations, including anticipated events. No reuse licence was found.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T02:17:23+00:00"),
)


def _one(root: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = root.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Missing or ambiguous JR Shikoku element: {selector}")
    return matches[0]


def _direct_text(tag: Tag) -> str:
    return " ".join(str(c).strip() for c in tag.find_all(string=True, recursive=False)
                    if not isinstance(c, Comment) and str(c).strip())


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    summary_tag = _one(soup, ".delay_status > a")
    summary = _direct_text(summary_tag)
    if not summary:
        raise ParseError("Empty JR Shikoku summary")
    known = summary in _SUMMARIES and set(summary_tag.get_attribute_list("class")) == _SUMMARIES[summary]
    overlays: dict[str, str] = {}
    for layer in _one(soup, ".mapbase").select(":scope > .maplayer"):
        map_keys = [c.removeprefix("ml_") for c in layer.get_attribute_list("class") if c.startswith("ml_")]
        if len(map_keys) != 1 or map_keys[0] not in _ROUTES or map_keys[0] in overlays:
            raise ParseError("Unknown or duplicate JR Shikoku map section")
        overlays[map_keys[0]] = re.sub(r"\s+", "", str(layer.get("style", ""))).rstrip(";")
    if set(overlays) != set(_ROUTES):
        raise ParseError("Incomplete JR Shikoku map")
    active = {key for key, style in overlays.items() if style == "display:block"}
    uncertain = {key for key, style in overlays.items() if style not in ("", "display:none", "display:block")}
    entries = _one(soup, ".delay_info > dl").select(":scope > dt, :scope > dd")
    if len(entries) % 2 or any(tag.name != ("dt" if i % 2 == 0 else "dd") for i, tag in enumerate(entries)):
        raise ParseError("Unpaired JR Shikoku incident headings and details")
    if known and summary == _NORMAL and (entries or active):
        raise ParseError("JR Shikoku normal summary conflicts with incidents or map")
    if known and summary != _NORMAL and not entries:
        raise ParseError("Missing JR Shikoku incident details")
    alerts: dict[str, list[ServiceAlert]] = {key: [] for key in _ROUTES}
    times: dict[str, list[datetime]] = {key: [] for key in _ROUTES}
    identifiers: set[str] = set()
    for i in range(0, len(entries), 2):
        heading, detail = entries[i:i + 2]
        identifier = str(heading.get("dinfo_id", ""))
        if identifier != str(detail.get("dinfo_id", "")) or (identifier and identifier in identifiers):
            raise ParseError("Mismatched or duplicate JR Shikoku incident ID")
        if identifier:
            identifiers.add(identifier)
        title_tag = _one(heading, "h2")
        route, title = _direct_text(title_tag), title_tag.get_text(" ", strip=True)
        body = _one(detail, ".detail_txt").get_text("\n", strip=True)
        time_text = _one(detail, ".upd_time").get_text(strip=True)
        if not title or not body or not re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}更新", time_text):
            raise ParseError("Empty JR Shikoku notice or invalid source update time")
        updated_at = datetime.strptime(time_text, "%Y/%m/%d %H:%M更新").replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        keys = _HEADINGS.get(route, ())
        targets = tuple(key for key in keys if key in active) or keys
        status = LineStatus.UNKNOWN if (route and not keys) or not known else LineStatus.ALERT
        alert = make_alert(lines[0], status, title, body,
                           affected_line_ids=tuple(_ROUTES[key] for key in targets))
        for key in targets or tuple(_ROUTES):
            alerts[key].append(alert)
            times[key].append(updated_at)
            if status is LineStatus.UNKNOWN:
                uncertain.add(key)
    for key in active:
        if not alerts[key]:
            raise ParseError(f"JR Shikoku highlighted section has no notice: {key}")
    result: list[Line] = []
    for line in lines:
        key = next(key for key, identifier in _ROUTES.items() if identifier == line.line_id)
        status = (LineStatus.UNKNOWN if not known or key in uncertain else
                  LineStatus.ALERT if alerts[key] else LineStatus.NORMAL)
        if status is LineStatus.UNKNOWN:
            alerts[key].append(make_alert(line, status, summary, f"{summary}; map={overlays[key]}", affected_line_ids=()))
        result.append(snapshot(line, status, summary, fetched_at, alerts=tuple(alerts[key]),
                               updated_at=max(times[key]) if times[key] else None,
                               source_line_names=(line.name,)))
    return tuple(result)


class JrShikokuProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[i].create_line(_ID, _URL) for i in _ROUTES.values()), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content.decode("utf-8-sig"), self.lines, self._now())

    def _route(self, key: str) -> Line:
        return next(line for line in self.lines if line.line_id == _ROUTES[key])

    @property
    def seto_ohashi(self) -> Line:
        return self._route("seto")

    @property
    def yosan_takamatsu_matsuyama(self) -> Line:
        return self._route("yosan1")

    @property
    def yosan_matsuyama_uwajima(self) -> Line:
        return self._route("yosan2")

    @property
    def dosan_tadotsu_kochi(self) -> Line:
        return self._route("dosan1")

    @property
    def dosan_kochi_kubokawa(self) -> Line:
        return self._route("dosan2")

    @property
    def kotoku(self) -> Line:
        return self._route("kotoku")

    @property
    def mugi(self) -> Line:
        return self._route("mugi")

    @property
    def tokushima(self) -> Line:
        return self._route("tokushima")

    @property
    def naruto(self) -> Line:
        return self._route("naruto")

    @property
    def yodo(self) -> Line:
        return self._route("yodo")
