# Keio official source evidence

Investigation combined both public-source inspection and the Wayback Machine,
2026-11-03 UTC.

## What the page actually loads

The human-facing page
[unkou_pc.html](https://www.keio.co.jp/unkou/unkou_pc.html) (and its
`unkou_pc_e/_c/_k.html` siblings) server-renders the current message inside
`<div class="c-bg-box unko_txt"><p class="c-text__normal status">`, matching
what the page polls on load and on its "更新" button at
`https://www.keio.co.jp/_system/_unkou/unkouInformation.xml`
(`/cmn_js/unkou_time.js`, charset Shift_JIS, confirms this with
`targetXmlPath = "../_system/_unkou/unkouInformation.xml"` and a jQuery AJAX
GET that reads `$(xml).find("emergency"|"unkouInformation"|"time")`). That
script only updates the displayed clock (`#unkouTime`) and a loading
indicator; it is not an alternate data source. `/cmn_js/unkou_cookie_manager.js`
only stores the auto-refresh interval cookie `keio.auto.update.interval` and
carries no status data. Both scripts were captured live and are in
`reports/candidate_scan/probe_keio_time_js.html` and
`probe_keio_cookie_js.html` (not fixtures; research artifacts only).

The XML root is `<unkou>` with exactly three always-present children in every
capture found: `<emergency>` (`"true"`/`"false"`), `<unkouInformation>`
(free-text Japanese), and `<time>` (`YYYY/MM/DD HH:MM`, no explicit offset;
treated as `Asia/Tokyo`, matching the page's own Japanese-locale
rendering). Newer captures add `<imgTime>` (always empty in every capture
seen) and `<lang_time>` (the same time in a different, Japanese-labelled
format); neither is used.

## Normal evidence (live + 14 years of archive)

A live GET on 2026-11-03T03:40:56Z and Wayback CDX captures for
`www.keio.co.jp/_system/_unkou/unkouInformation.xml` from 2011-05-31 through
2024-05-30 (`20110531012037`, `20120531130140`, `20190328110503`,
`20191002081425`, `20191215010908`, `20200308151851`, `20200606150058`,
`20200905202713`, `20201206222130`, `20210305143638`, `20210607004215`,
`20211012095523`, `20240530150807`) are **all** `emergency=false` with the
exact fixed sentence `"京王線・井の頭線は平常通り運転しています。"` (an
earlier 2011/2012 wording difference was also `emergency=false`). The
`20240530150807` capture is also where the XML's own `encoding` attribute and
byte encoding switch from Shift_JIS to UTF-8 — the same encoding the live
2026 response uses. `keio_normal.xml` is the live 2026-11-03 UTF-8 capture,
byte-for-byte, used directly (no extraction).

## The one abnormal capture found

CDX listed exactly one capture with `emergency=true`:
`20190909043234` (2019-09-09T04:32:34Z), Shift_JIS, body
`"井の頭線　運転を見合せています"` ("Inokashira Line: service suspended"),
naming only one of the two groups the normal sentence names together.
`keio_20190909043234.xml` preserves these exact archived bytes.

**CPython's expat-based `xml.etree.ElementTree` cannot decode bytes whose XML
prolog declares a multi-byte encoding** (`ValueError: multi-byte encodings
are not supported`); Shift_JIS is multi-byte. Feeding `keio_20190909043234.xml`
to the provider therefore raises `ParseError` (caught by the shared
`SnapshotProvider._refresh_lines`, previous snapshot kept) rather than being
parsed as an incident — `tests/test_keio.py::
test_shift_jis_declared_xml_is_a_parse_error_not_a_crash` records this real,
observed limitation rather than hiding it. Because the live site has used
UTF-8 since at least 2024, this does not affect current production behaviour.

To exercise the emergency-flag/alert logic against this real incident's own
text, `keio_20190909043234_utf8.xml` re-encodes the same decoded characters as
UTF-8 (prolog's `encoding` attribute updated to match); no tag, value, or
character was changed, only the byte encoding. This is a documented synthetic
transcoding of real data, not a new or modified capture — see
`keio_manifest.json`.

## Why `emergency=true` does not get decomposed by line

With a single abnormal sample, and no documented stable template that
separates a named group from the rest of the sentence (the normal sentence
names both groups together; the one abnormal sample names only one), per-line
attribution from this free text is not established as a safe, general rule.
`emergency=false` together with the exact fixed sentence is therefore the
only basis for `NORMAL`, applied identically to the seven canonical lines this
single network-wide XML covers together (Keio does not publish a separate feed
per line or branch). Any other `<emergency>` value — `"true"`, or any
unrecognized future value — and `emergency=false` with any other body (not
observed; synthetic test only) keep every line `UNKNOWN` with one shared alert carrying the raw
body and `affected_line_ids=()`. This mirrors the existing Hanshin/Osaka
Monorail treatment of whole-network, line-unidentified notices (see the main
[README](../../README.md) and `tests/fixtures/SOURCES.md`).

## Terms

[サイトのご利用にあたって](https://www.keio.co.jp/contact/site/), reviewed
2026-11-03, 著作権について: "当サイト上のコンテンツに関する著作権は、原則
として当社が有しております。当サイト上に掲載されている全ての...データ等の
利用については、複製・転用・転載・電磁的加工・送信・頒布・二次的使用・その
他これらに類する全ての行為も含め、一切お断りいたします。" — reproduction,
repurposing, reprinting, electronic processing, transmission, distribution
and secondary use of all site content are declined without exception; no
private-use carve-out is stated. This is recorded as `PERMISSION_REQUIRED`.
The operation page itself (checked the same day) separately discloses a
roughly 15-minute delay threshold and disclaims the accuracy/timeliness of
published information; it is recorded as `additional_terms_urls`.

## Not covered

No per-line or per-branch breakdown (京王線 vs. its Shinsen/Sagamihara/Takao/
Keibajo/Doubutsuen extensions, vs. Inokashira) is published by this feed; nor
is a delay-only code, incident validity period, or any field besides the
three described above. `imgTime`/`lang_time` are not used (see above).
