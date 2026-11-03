# Seibu Railway evidence

Retrieved on 2026-11-03 UTC with httpx/curl GET, redirects enabled, a standard
browser User-Agent (the default httpx/curl User-Agent also returned HTTP 200,
so no special header is required or sent by the provider). The
[manifest](seibu_manifest.json) records source URLs, UTC capture times and
SHA-256 hashes of complete downloaded originals and of the extracted fixtures.

## What was investigated

- Human-facing pages: <https://www.seiburailway.jp/> (home widget) and
  <https://www.seiburailway.jp/railway/railwayinfo/> (detail page). Both embed
  the same `.js-railwaysInfo` widget; only the home page's markup includes the
  static `.js-railwaysInfoLine > li` list of exactly twelve official line
  names, preserved verbatim in
  [seibu_home_widget_excerpt.html](seibu_home_widget_excerpt.html): 池袋線,
  西武秩父線, 西武有楽町線, 豊島線, 狭山線, 山口線, 新宿線, 拝島線, 西武園線,
  国分寺線, 多摩湖線, 多摩川線. These twelve names are mutually exclusive
  substrings of one another and of the one special literal `西武線全線`
  ("all Seibu lines"), which this provider also treats specially.
- Public JavaScript: [script.js](https://www.seiburailway.jp/assets/js/script.js)'s
  `railwaysInfo()` function, excerpted unmodified in
  [seibu_script_excerpt.js](seibu_script_excerpt.js). `getXml()` issues
  `GET /api/v1/travelinfo/raw/IDS2Web.xml?<random>` with cache-busting headers.
  `getLine()` reads `info/dif` (`all` count, `lif` children each with
  `lin/nm` and `sts/nm`) and `info/tif` (map-pattern numbers, used only to pick
  an illustration image). For each `lif`, if `lin/nm` equals exactly
  `西武線全線` the entry is treated as applying to every line (strict `===`);
  otherwise matching is `tempLine.match(item2.innerText)`, i.e. each mini-list
  item's short name is used as a (sub)string test against the XML's `lin/nm`.
  If `sts/nm` is exactly `運転見合わせ`, `運転再開見込` or `運休` the matching
  item gets CSS class `stop`; any other non-empty `sts/nm` only gets `caution`.
  The code never further distinguishes delay from partial suspension. `getTxt()`
  separately reads `info/txt` (the overall Japanese notice) and shows it
  regardless of `dif`'s contents, styled as `caution` only when some `lif`
  existed.
- Public JavaScript:
  [seiburailways.core.js](https://www.seiburailway.jp/assets/js/seiburailways.core.js),
  saved whole (1268 bytes) as
  [seibu_core_excerpt.js](seibu_core_excerpt.js). Its `operation()` function
  calls a **different**, JSONP endpoint, confirmed live:
  `GET /api/v1/servicestatus.jsonp` (callback `sr_servicestatus_callback`),
  and renders only `IDS2Web[].plf.pld[].lang_ja` entries as a
  "重要なお知らせ"-style banner placed *before* `.js-railwaysInfo`. The live
  response, saved unmodified as
  [seibu_servicestatus_jsonp.txt](seibu_servicestatus_jsonp.txt), has **no**
  `dif`/`tif` fields at all:
  `{"IDS2Web":[{"status_code":200,"time":"...","text":"...","chk":0,"tif_all":0,"tif":[{"pif":[]}],"plf_all":0,"plf":{"pld":[]}}]}`.
  This confirms `plf`/`pld` (also present but unused in the XML's `info/plf`)
  is a structurally separate long-term/important-notice channel from the
  per-line `dif` status, analogous to JR West's `areaAnnouncements` or JR
  Kyushu's long-term-suspension flag file. This provider does not request
  `/api/v1/servicestatus.jsonp` and does not parse `tif` or `plf`.
- The live XML itself,
  [seibu_normal.xml](seibu_normal.xml) (the no-incident state; `dif`/`tif`/`plf`
  all `all="0"`, `info/txt` empty, `chk=0`). A re-check roughly 75 minutes
  later returned the same all-zero content but with a newer `<time>` value,
  showing the document is regenerated periodically by the source even while
  normal, not purely on incident/recovery events; `<time>` is still the
  source's own declared document timestamp, not a request time, and is used
  as `updated_at` (Asia/Tokyo).

## What was not found

Wayback Machine CDX was queried for `seiburailway.jp/api/v1/travelinfo/*`
(both the exact XML URL and that path as a prefix): zero captures exist, so
the XML endpoint has apparently never been crawled. CDX for
`seiburailway.jp/railway/railwayinfo/index.html` lists ten captures
(2022-2026), but all are server-rendered HTML with the default
`icon_normal.png` and no `.js-railwaysInfoLine` widget on that particular
page; they do not reflect the live XML's state and cannot confirm an abnormal
response. No real disruption sample of `IDS2Web.xml` with non-empty `dif` was
found anywhere (ODPT publishes Seibu data only under its challenge-only
licence and was not used, per the task's constraint).

## Status mapping and its evidence

| Verified source signal | Common status | Evidence |
| --- | --- | --- |
| `sts/nm` exactly `運転見合わせ`, `運転再開見込` or `運休` | `SUSPENDED` | `script.js` `getLine()` adds CSS class `stop` for exactly these three strings and no others |
| any other non-empty `sts/nm` | `ALERT` | same function only adds generic `caution`; it never distinguishes delay from partial suspension, so neither is inferred |
| `lin/nm` exactly `西武線全線` | applies to all eleven catalog lines | `script.js` checks `tempLine === '西武線全線'` with strict equality before falling back to substring matching |
| other `lin/nm` | matched by substring containment against the twelve verified official names | mirrors `tempLine.match(item2.innerText)`; the twelve names are confirmed mutually exclusive substrings, so this is deterministic |
| unrecognized `lin/nm` | `ParseError` (previous snapshot kept) | the twelve-name universe was itself verified live, not inferred from prose; an unmatched name indicates either a site change or a different, unverified publication unit, so this provider refuses to guess rather than assign `UNKNOWN` |
| `info/txt` non-empty with no `dif` entries | one `ALERT` with `affected_line_ids=()`, downgrading otherwise-`NORMAL` lines to `UNKNOWN` | mirrors the already-reviewed Tokyu provider's handling of the same ambiguity (see `tests/fixtures/TOKYU.md`); Seibu's own JS shows this text regardless of scope |
| `dif all="0"` and no entries | `NORMAL` | the only state observed live |

`timing` is left `UNKNOWN` for every alert. This provider is not one of the
README's enumerated ACTIVE-timing sources (JR West, JR East, Yahoo), and no
dedicated applicability field was found for Seibu.

## Synthetic vs. real

Only the no-incident XML is real. Every suspended/alert/network-wide-marker/
unscoped-notice/unknown-name/ambiguous-name/malformed-structure case in
`tests/test_seibu.py` is a synthetic mutation of `seibu_normal.xml`, built
strictly from the branching documented above (three exact suspension labels,
one exact "all lines" literal, substring matching against the twelve verified
names, and the separate `info/txt`/`dif` scoping already established for
Tokyu). No real Seibu disruption, partial-suspension-specific wording, or
`info/plf` content was observed; if the live site ever introduces a label the
official UI itself distinguishes beyond stop/caution, this provider would not
detect that distinction.

## Terms

Reviewed 2026-11-03 UTC. The
[operation-information page](https://www.seiburailway.jp/railway/railwayinfo/)
states: 「この情報を無断で転載・複写すること、また、体裁を変更するなどして
Webサイトなどで公開することを固く禁じます。」(unauthorized reproduction or
copying of this information, including republishing it with altered
formatting on other websites, is strictly prohibited) and separately states a
15-minutes-or-more delay publication threshold. The site-wide
[サイトのご利用にあたって](https://www.seiburailway.jp/policy/) page's
"著作権について" section separately reserves statutory private use
(「私的利用の範囲を超えて...複製・転用・転載・頒布する行為...を禁止します」)
and requires the rightsholder's permission beyond that; no service-specific
commercial-reuse grant was found. Metadata records `PERMISSION_REQUIRED`,
consistent with the similarly-worded Keisei and Keihan providers.
