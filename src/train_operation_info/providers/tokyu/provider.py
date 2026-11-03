"""Tokyu's official public service information for nine lines.

Investigation: public HTML/JavaScript inspection on 2026-11-02, at
https://www.tokyu.co.jp/unten2/unten.html and
https://www.tokyu.co.jp/themes/custom/tokyu_portal2/bundle/main.js?tn94mu.
The hl() function reads /unten/unten2.json, /unten/unten_additional.json and
/unten/information.json. check_<route> contains two comma-separated codes:
the first controls detail display (0 hidden, 1 shown, 2 replacement transport),
the second the icon (0 circle, 1/3 triangle, 2 cross). The page legend defines
triangle as mixed information, including delays, cancellations and through
service changes: it is ALERT, never automatically DELAYED. Cross establishes
suspension but does not establish whether it is partial or full-line.
The page's current clock is generated with new Date(), not a source update.
kousin_jikoku was null in live JSON; non-null formats/semantics are unverified,
so updated_at remains None and nonempty raw values are kept in alert prose.
Only the nine route codes displayed by the official script are covered;
Minatomirai is not a separate route in this feed. Replacement transport lists
and map images are not imported. Global notices retain unidentified scope.
CDX listed abnormal captures but replay returned HTTP 429; abnormal and
recovery tests are synthetic, based on the published code mapping. Evidence,
hashes and limitations: tests/fixtures/TOKYU.md.
"""

import re
from datetime import datetime
from typing import Final

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from pydantic import BaseModel, ConfigDict, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.tokyu.co.jp/unten2/unten.html"
_BASE: Final = "https://www.tokyu.co.jp/unten/"
_ID: Final = ProviderId("tokyu")
# Reuse the canonical IDs already shared by the Yahoo provider.
_ROUTES: Final = (
    ("ty", "東横線", LineId("jp:tokyu:line_965f1b018f36")),
    ("mg", "目黒線", LineId("jp:tokyu:line_03de25366237")),
    ("sh", "東急新横浜線", LineId("jp:tokyu:line_80065b958e40")),
    ("dt", "田園都市線", LineId("jp:tokyu:line_65171aeb7d8c")),
    ("om", "大井町線", LineId("jp:tokyu:line_e9ca4aaa4764")),
    ("ik", "池上線", LineId("jp:tokyu:line_a3e6707bf08d")),
    ("tm", "東急多摩川線", LineId("jp:tokyu:line_4268fea72783")),
    ("sg", "世田谷線", LineId("jp:tokyu:line_4a77de8e8446")),
    ("kd", "こどもの国線", LineId("jp:tokyu:line_ad0499ddb335")),
)
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_BASE + "unten2.json", method="GET", format=DataFormat.JSON,
            description='Route status',
        ),
        SourceEndpoint(
            url=_BASE + "unten_additional.json", method="GET", format=DataFormat.JSON,
            description='Additional notices',
        ),
        SourceEndpoint(
            url=_BASE + "information.json", method="GET", format=DataFormat.JSON,
            description='General information',
        ),
    ),
    provider_id=_ID, name="Tokyu official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.tokyu.co.jp/use/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note="Site terms section 3 reserves personal private use and uses "
    "allowed by law; other copying, modification, redistribution and public "
    "display require prior permission. This is not a public-signage licence. "
    "The operation page publishes delays of 15 minutes or more and suspensions.",
    reviewed_at=datetime.fromisoformat("2026-11-02T02:12:22+00:00"),
)


class _Source(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Status(_Source):
    check: str
    unten: str
    kousin_jikoku: str | None
    check_ty: str
    unten_ty: str
    check_mg: str
    unten_mg: str
    check_sh: str
    unten_sh: str
    check_dt: str
    unten_dt: str
    check_om: str
    unten_om: str
    check_ik: str
    unten_ik: str
    check_tm: str
    unten_tm: str
    check_sg: str
    unten_sg: str
    check_kd: str
    unten_kd: str

    def records(self) -> tuple[tuple[str, str], ...]:
        return (
            (self.check_ty, self.unten_ty), (self.check_mg, self.unten_mg),
            (self.check_sh, self.unten_sh), (self.check_dt, self.unten_dt),
            (self.check_om, self.unten_om), (self.check_ik, self.unten_ik),
            (self.check_tm, self.unten_tm), (self.check_sg, self.unten_sg),
            (self.check_kd, self.unten_kd),
        )


class _Additional(_Source):
    message: str


class _Information(_Additional):
    check: str


def _text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style"):
        tag.decompose()
    for tag in soup.select("br"):
        tag.replace_with(NavigableString("\n"))
    return soup.get_text("\n", strip=True)


def _parse(
    data: _Status, additional: _Additional, information: _Information,
    lines: tuple[Line, ...], fetched_at: datetime,
) -> tuple[Line, ...]:
    if not data.check or not information.check or not _text(data.unten):
        raise ParseError("Tokyu overall operating message is empty")
    if information.check != "0" and not _text(information.message):
        raise ParseError("Tokyu enabled information message is empty")
    notices = [additional.message]
    if information.check != "0":
        notices.append(information.message)
    if data.check not in ("0", "1", "2"):
        notices.append(f"check={data.check}\n{data.unten}")
    elif data.check != "0" and all(code == "0,0" for code, _ in data.records()):
        notices.append(data.unten)
    shared = tuple(make_alert(
        lines[0], LineStatus.UNKNOWN, "東急: お知らせ（対象路線未特定）",
        _text(message), affected_line_ids=(),
    ) for message in notices if _text(message))
    result: list[Line] = []
    for line, (_, name, _), (codes, raw_message) in zip(lines, _ROUTES, data.records()):
        if re.fullmatch(r"\d+,\d+", codes) is None:
            raise ParseError("Tokyu route status code is missing or malformed")
        details, icon = codes.split(",")
        message = _text(raw_message)
        if not message:
            raise ParseError("Tokyu route operating message is empty")
        if data.check == "0" and codes != "0,0":
            raise ParseError("Tokyu normal summary conflicts with route status")
        status = {
            "0": LineStatus.NORMAL, "1": LineStatus.ALERT,
            "2": LineStatus.SUSPENDED, "3": LineStatus.ALERT,
        }.get(icon, LineStatus.UNKNOWN)
        if details not in ("0", "1", "2") or data.check not in ("0", "1", "2"):
            status = LineStatus.UNKNOWN
        if status is LineStatus.NORMAL and message != f"{name}は、平常通り運転しています。":
            status = LineStatus.UNKNOWN
        label = f"check={codes}\n{message}"
        description = message
        if data.kousin_jikoku:
            description += f"\nkousin_jikoku: {data.kousin_jikoku}"
        alerts = shared
        if status is not LineStatus.NORMAL:
            title = {
                LineStatus.ALERT: "運行情報あり",
                LineStatus.SUSPENDED: "運転見合わせ",
            }.get(status, "未確認の運行情報")
            alerts += (make_alert(line, status, f"{name}: {title}", description),)
        elif shared:
            status = LineStatus.UNKNOWN
        result.append(snapshot(
            line, status, label, fetched_at, alerts=alerts,
            source_line_names=(name,),
        ))
    return tuple(result)


class TokyuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL)
            for _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _BASE + "unten2.json")
        response.raise_for_status()
        data = _Status.model_validate_json(response.content.decode("utf-8-sig"))
        additional = await self._get(client, _BASE + "unten_additional.json")
        additional.raise_for_status()
        information = await self._get(client, _BASE + "information.json")
        information.raise_for_status()
        return _parse(
            data, _Additional.model_validate_json(additional.content.decode("utf-8-sig")),
            _Information.model_validate_json(information.content.decode("utf-8-sig")),
            self.lines, self._now(),
        )

    @property
    def toyoko(self) -> Line:
        return self._line("line_965f1b018f36")

    @property
    def meguro(self) -> Line:
        return self._line("line_03de25366237")

    @property
    def shin_yokohama(self) -> Line:
        return self._line("line_80065b958e40")

    @property
    def den_en_toshi(self) -> Line:
        return self._line("line_65171aeb7d8c")

    @property
    def oimachi(self) -> Line:
        return self._line("line_e9ca4aaa4764")

    @property
    def ikegami(self) -> Line:
        return self._line("line_a3e6707bf08d")

    @property
    def tamagawa(self) -> Line:
        return self._line("line_4268fea72783")

    @property
    def setagaya(self) -> Line:
        return self._line("line_4a77de8e8446")

    @property
    def kodomonokuni(self) -> Line:
        return self._line("line_ad0499ddb335")
