"""Keisei official service alerts.

Investigation: both archives and public HTML/JavaScript inspection, 2026-11-02.
https://www.keisei.co.jp/traininfo/index.php supplies #info_dif (Japanese
route/status, cause, section) and #info_txt (narrative). Wayback captures
20260415104003, 20260516001941, 20260813101347 and 20261016114304 verify
運転見合わせ/cls1, 一部運休/cls2 and 遅れ/cls2. cls2 alone cannot distinguish
delay from partial cancellation. Capture 20260903013656 and live HTML verify
京成線 平常運行/cls0. Unlisted monitored routes have no published incident;
only these six verified publication units are exposed. Higashi-Narita is not
separately verified. Chiba/Chihara share the existing canonical group ID.

https://www.keisei.co.jp/traininfo/data/notice.js and data/kccmod.js supply a
Japanese notice gated by ja_flg and an exclusive s_day/e_day interval. These
public scripts were inspected without executing JavaScript. Active-notice and
malformed/unknown cases are synthetic tests. Archived HTML does not prove the
contemporaneous contents of separately fetched notice.js. No same-incident
recovery capture was verified; normal HTML tests clearing old incidents.

#time says 現在 and tracks page generation even during unchanged normal service;
it is not a source update timestamp. updated_at is therefore None. History,
route-map images, train positions and delay certificates are not fetched.
Fixture URLs, UTC capture times, extraction and hashes: tests/fixtures/KEISEI.md.
"""

import ast
from datetime import datetime
import re
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pathlib import Path

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.keisei.co.jp/traininfo/index.php"
_NOTICE_URL: Final = "https://www.keisei.co.jp/traininfo/data/notice.js"
_ID: Final = ProviderId("keisei")
_TOKYO: Final = ZoneInfo("Asia/Tokyo")
# Source labels, public properties, existing canonical IDs (also used by Yahoo).
_ROUTES: Final = (
    ("京成本線", "main", LineId("jp:keisei:line_e96ffc09d83a")),
    ("成田スカイアクセス線", "narita_sky_access", LineId("jp:keisei:line_5e3c730ed219")),
    ("押上線", "oshiage", LineId("jp:keisei:line_4c0010d67413")),
    ("金町線", "kanamachi", LineId("jp:keisei:line_3e3f536f0c12")),
    ("千葉線･千原線", "chiba_chihara", LineId("jp:keisei:line_9c8d3cb5f81a")),
    ("松戸線", "matsudo", LineId("jp:keisei:line_780859fc9d46")),
)
_STATES: Final = {
    "平常運行": ("cls0", LineStatus.NORMAL),
    "遅れ": ("cls2", LineStatus.DELAYED),
    "一部運休": ("cls2", LineStatus.PARTIAL_SUSPENSION),
    "運転見合わせ": ("cls1", LineStatus.SUSPENDED),
}
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Route status and incident details',
        ),
        SourceEndpoint(
            url=_NOTICE_URL, method="GET", format=DataFormat.JAVASCRIPT,
            description='Time-limited notices',
        ),
    ),
    provider_id=_ID, name="Keisei official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl(_URL), additional_terms_urls=(),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The service page prohibits unapproved reproduction, copying and "
    "publication, including reformatted publication on websites. No separate "
    "general site reuse terms were located in the inspected navigation. "
    "The source reports delays of approximately 15 minutes or more, including "
    "expected delays; NORMAL refers to that publication threshold.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T02:20:00+00:00"),
)


def _route_name(text: str) -> str:
    return text.replace("・", "･").strip()


def _notice_string(script: str, name: str) -> str:
    matches = re.findall(rf"\bvar\s+{name}\s*=\s*('(?:\\.|[^'\\])*')\s*;", script)
    if len(matches) != 1:
        raise ParseError(f"Missing or duplicate Keisei notice field: {name}")
    # Parse a string literal only; never execute downloaded JavaScript.
    try:
        value = ast.literal_eval(matches[0])
    except (SyntaxError, ValueError) as exc:
        raise ParseError(f"Invalid Keisei notice string: {name}") from exc
    if not isinstance(value, str):
        raise ParseError(f"Invalid Keisei notice type: {name}")
    return value


def _parse_notice(script: str, fetched_at: datetime) -> str | None:
    flags = re.findall(r"\bvar\s+ja_flg\s*=\s*([01])\s*;", script)
    if len(flags) != 1:
        raise ParseError("Missing or invalid Keisei Japanese notice flag")
    if flags[0] == "0":
        return None
    dates: list[datetime] = []
    for name in ("s_day", "e_day"):
        values = re.findall(rf"\bvar\s+{name}\s*=\s*new Date\('([^']+)'\)\s*;", script)
        if len(values) != 1:
            raise ParseError(f"Missing or duplicate Keisei notice date: {name}")
        parsed = datetime.strptime(values[0], "%Y-%m-%dT%H:%M:%S")
        dates.append(parsed.replace(tzinfo=_TOKYO))
    if dates[0] >= dates[1]:
        raise ParseError("Invalid Keisei notice interval")
    text = BeautifulSoup(_notice_string(script, "ja_txt"), "html.parser").get_text("\n", strip=True)
    if not text:
        raise ParseError("Empty enabled Keisei notice")
    return text if dates[0] < fetched_at < dates[1] else None


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime,
           notice: str | None) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select("#info_dif > .ja")
    if len(containers) != 1:
        raise ParseError("Missing or duplicate Keisei Japanese status section")
    rows = containers[0].select(":scope > dl")
    if not rows:
        raise ParseError("Empty Keisei status section")
    names = {_route_name(name) for name, _, _ in _ROUTES}
    statuses: dict[str, tuple[LineStatus, str, str]] = {}
    normal = False
    for row in rows:
        headings = row.select(":scope > dt")
        details = row.select(":scope > dd")
        if len(headings) != 1 or not details or any(not d.get_text(strip=True) for d in details):
            raise ParseError("Incomplete Keisei status row")
        title = headings[0].get_text(" ", strip=True)
        parts = title.split()
        if len(parts) != 2:
            raise ParseError("Invalid Keisei route/status heading")
        name, label = _route_name(parts[0]), parts[1]
        known = _STATES.get(label)
        status = known[1] if known is not None and row.get("class") == [known[0]] else LineStatus.UNKNOWN
        if name == "京成線":
            if len(rows) == 1 and status is LineStatus.UNKNOWN:
                description = row.get_text("\n", strip=True)
                for body_node in soup.select("#info_txt > #jp_txt"):
                    description += "\n\n" + body_node.get_text("\n", strip=True)
                alerts: tuple[ServiceAlert, ...] = (
                    make_alert(lines[0], status, title, description, affected_line_ids=()),
                )
                if notice is not None:
                    alerts += (make_alert(lines[0], LineStatus.ALERT, "京成線のお知らせ", notice, affected_line_ids=()),)
                return tuple(snapshot(line, status, title, fetched_at, alerts=alerts,
                                      source_line_names=(source_name,))
                             for line, (source_name, _, _) in zip(lines, _ROUTES))
            if len(rows) != 1 or status is not LineStatus.NORMAL or details[0].get_text(strip=True) != "現在、京成線は平常どおり運行しています。":
                raise ParseError("Conflicting Keisei all-lines normal statement")
            normal = True
        elif name not in names or name in statuses or label == "平常運行":
            raise ParseError(f"Unknown, duplicate or inconsistent Keisei route: {name}")
        elif len(details) != 2 or not details[0].get_text(strip=True).startswith("原因…") or not details[1].get_text(strip=True).startswith("区間…"):
            raise ParseError("Missing Keisei incident cause or section")
        statuses[name] = (status, label, row.get_text("\n", strip=True))

    descriptions: dict[str, str] = {}
    body_nodes = soup.select("#info_txt > #jp_txt")
    if not normal:
        if len(body_nodes) != 1:
            raise ParseError("Missing or duplicate Keisei incident narrative")
        body = body_nodes[0].get_text("\n", strip=True)
        headings_in_body = list(re.finditer(r"【([^【】]+)[：:]([^【】]+)】", body))
        if not headings_in_body or body[:headings_in_body[0].start()].strip():
            raise ParseError("Invalid Keisei incident narrative headings")
        for index, heading in enumerate(headings_in_body):
            name = _route_name(heading.group(1))
            if name not in statuses or name in descriptions:
                raise ParseError(f"Unmatched Keisei incident narrative: {name}")
            end = headings_in_body[index + 1].start() if index + 1 < len(headings_in_body) else len(body)
            if not body[heading.end():end].strip():
                raise ParseError("Empty Keisei incident narrative")
            descriptions[name] = body[heading.start():end].strip()
        if set(descriptions) != set(statuses):
            raise ParseError("Keisei status and narrative coverage disagree")
    elif body_nodes:
        raise ParseError("Keisei normal statement has incident narrative")

    global_alerts = () if notice is None else (
        make_alert(lines[0], LineStatus.ALERT, "京成線のお知らせ", notice, affected_line_ids=()),
    )
    result: list[Line] = []
    for line, (name, _, _) in zip(lines, _ROUTES):
        key = _route_name(name)
        status, label, summary = statuses.get(key, (LineStatus.NORMAL, "平常運行", ""))
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{name}：{label}", summary + "\n\n" + descriptions[key]),
        )
        if notice is not None and status is LineStatus.NORMAL:
            status = LineStatus.ALERT
        result.append(snapshot(line, status, label, fetched_at, alerts=alerts + global_alerts,
                               source_line_names=(name,)))
    return tuple(result)


class KeiseiProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[i].create_line(_ID, _URL) for _, _, i in _ROUTES), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        notice = await self._get(client, _NOTICE_URL)
        notice.raise_for_status()
        fetched_at = self._now()
        return _parse(response.text, self.lines, fetched_at, _parse_notice(notice.text, fetched_at))

    def _route(self, key: str) -> Line:
        identifier = next(identifier for _, attr, identifier in _ROUTES if attr == key)
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def main(self) -> Line:
        return self._route("main")

    @property
    def narita_sky_access(self) -> Line:
        return self._route("narita_sky_access")

    @property
    def oshiage(self) -> Line:
        return self._route("oshiage")

    @property
    def kanamachi(self) -> Line:
        return self._route("kanamachi")

    @property
    def chiba_chihara(self) -> Line:
        return self._route("chiba_chihara")

    @property
    def matsudo(self) -> Line:
        return self._route("matsudo")
