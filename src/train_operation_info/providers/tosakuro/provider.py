"""Tosa Kuroshio's official two service-information articles.

Investigation: public HTML inspection and Wayback HTML, 2026-11-04 UTC.
https://www.tosakuro.com/ renders two route-specific post lists inside
#comp-m9tlcfob. Their headings identify Gomen-Nahari and Nakamura/Sukumo,
matching the existing Yahoo catalog units. The extra combined/mobile list
is ignored. The route-specific list links, not article URL slugs or prose,
establish publication scope. Linked /post/ pages render h1[data-hook=post-title]
and section[data-hook=post-description]; no private API or account is needed.

Wayback home captures 20250902020512, 20260203070343, 20260709051932 and
20260825063025 show the complete title 平常運行. 20260609203918 also shows
平常運転 for Gomen-Nahari. Only these exact titles map to NORMAL; other titles
remain UNKNOWN. No abnormal status code, stable abnormal label mapping or
same-event recovery capture was verified. Unknown/failure/recovery tests are
synthetic. Pre-2026 route-list layouts (including 20250104050205 and
20250902020512) are not supported by the current structural selectors.

IMPORTANT: NORMAL describes the article's displayed headline only. A normal
headline can coexist with individual cancellations in its body (live official
article indexed on 2026-11-03). Every article body is therefore retained as an
OTHER informational alert, even for NORMAL. No narrative keyword determines
impact, affected lines or timing. affected_line_ids=(): the route panel is the
publication scope, not evidence that every service is affected. timing UNKNOWN,
active bounds None. Yearless '現在' prose and BlogPosting dateModified are not
verified operational update timestamps: updated_at=None.

Separate お知らせ/トピックス lists, including long-term cancellation articles,
are excluded structurally; mixed notices within the service article remain
intact. Timetables, positions, X and linked documents are not fetched. Raw home
recordings still contain excluded news. Terms were sought on the home/company
pages and their public links; no applicable reuse terms were found, so usage
permission is UNSPECIFIED, not a licence. Provenance, hashes and limitations:
tests/fixtures/TOSAKURO.md and tosakuro_manifest.json.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.tosakuro.com/"
_ID: Final = ProviderId("tosakuro")
_ROUTES: Final = (
    ("comp-m9tlcfoj", "comp-mf4wtprw", "ごめん・なはり線", LineId("jp:operator_3f08e3327220:line_ae624e7552d0")),
    ("comp-m9tlcfop", "comp-mf4wv5z1", "中村・宿毛線", LineId("jp:operator_3f08e3327220:line_f3ed2cf0c3d5")),
)
_NORMAL: Final = frozenset({"平常運行", "平常運転"})
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Tosa Kuroshio Railway official", source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_URL, method="GET", format=DataFormat.HTML,
                       description="Two route-specific service post lists; separate news excluded"),
        SourceEndpoint(url=_URL + "post/{slug}", method="GET", format=DataFormat.HTML,
                       is_template=True, description="Articles linked from the two service post lists"),
    ),
    terms_url=None, additional_terms_urls=(HttpUrl(_URL + "company-profile"),),
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note=(
        "No applicable reuse terms were found on the reviewed home/company pages "
        "and their links; public availability does not grant reuse permission. "
        "NORMAL reflects only the service headline; individual cancellations can "
        "coexist in its body. Every body is retained as an OTHER alert with unknown "
        "timing and affected lines. Separate news and linked documents are excluded."
    ),
    statuses=frozenset({LineStatus.NORMAL}),
    reviewed_at=datetime.fromisoformat("2026-11-04T12:14:55+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Tosa Kuroshio element missing or duplicated: {selector}")
    return matches[0]


def _posts(payload: bytes) -> tuple[tuple[str, str], ...]:
    soup = BeautifulSoup(payload, "html.parser")
    panel = _one(soup, "#comp-m9tlcfob")
    posts: list[tuple[str, str]] = []
    for heading_id, list_id, name, _ in _ROUTES:
        if _one(panel, f"#{heading_id} h1").get_text(strip=True) != name:
            raise ParseError("Tosa Kuroshio service route heading changed")
        listing = _one(panel, f"#{list_id}")
        title = _one(listing, '[data-hook="post-title"]')
        text = title.get_text(" ", strip=True)
        link = title.find_parent("a")
        if not text or not isinstance(link, Tag) or link not in listing.find_all("a"):
            raise ParseError("Tosa Kuroshio service post title/link missing")
        href = link.get("href")
        if not isinstance(href, str):
            raise ParseError("Tosa Kuroshio service post URL missing")
        url = urlsplit(href)
        if (url.scheme != "https" or url.netloc != "www.tosakuro.com"
                or url.query or url.fragment or not url.path.startswith("/post/")
                or not url.path.removeprefix("/post/")
                or "/" in unquote(url.path.removeprefix("/post/"))):
            raise ParseError("Unexpected Tosa Kuroshio service post URL")
        posts.append((text, href))
    if posts[0][1] == posts[1][1]:
        raise ParseError("Tosa Kuroshio route posts are duplicated")
    return tuple(posts)


def _article(payload: bytes, expected_title: str) -> str:
    soup = BeautifulSoup(payload, "html.parser")
    title = _one(soup, 'h1[data-hook="post-title"]').get_text(" ", strip=True)
    if title != expected_title:
        raise ParseError("Tosa Kuroshio listing and article titles disagree")
    body = _one(soup, 'section[data-hook="post-description"]')
    if body.select("script, style, iframe, template"):
        raise ParseError("Unexpected Tosa Kuroshio article content")
    text = body.get_text("\n", strip=True)
    if not text:
        raise ParseError("Tosa Kuroshio service article is empty")
    links: list[str] = []
    for link in body.select("a"):
        href = link.get("href")
        if not isinstance(href, str):
            raise ParseError("Tosa Kuroshio article link missing URL")
        links.append(str(HttpUrl(href)))
    # Preserve media destinations too; their contents/meaning are not inferred.
    for media in body.select("img"):
        src = media.get("src")
        if not isinstance(src, str):
            raise ParseError("Tosa Kuroshio article image missing URL")
        links.append(str(HttpUrl(src)))
    return "\n".join((text, *dict.fromkeys(links)))


class TosaKuroshioProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[key].create_line(_ID, _URL) for _, _, _, key in _ROUTES),
                         client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        posts = _posts(response.content)
        notices: list[tuple[Line, str, str, str]] = []
        for line, (title, url) in zip(self.lines, posts, strict=True):
            article = await self._get(client, url)
            article.raise_for_status()
            description = _article(article.content, title)
            notices.append((line, title, url, description))
        fetched_at = self._now()
        result: list[Line] = []
        for line, title, url, description in notices:
            alert = make_alert(line, LineStatus.ALERT, title, description, affected_line_ids=())
            alert = alert.model_copy(update={"source_url": HttpUrl(url)})
            result.append(snapshot(
                line, LineStatus.NORMAL if title in _NORMAL else LineStatus.UNKNOWN,
                title, fetched_at, alerts=(alert,),
            ))
        return tuple(result)

    @property
    def gomen_nahari(self) -> Line:
        return self._line("line_ae624e7552d0")

    @property
    def nakamura_sukumo(self) -> Line:
        return self._line("line_f3ed2cf0c3d5")
