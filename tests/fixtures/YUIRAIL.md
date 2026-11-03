# Yui Rail official operation notice

Reviewed 2026-11-02 UTC. The [top page](https://www.yui-rail.co.jp/) renders the
運行情報 marquee in `p.js-opt-info-text`.
[layout.min.js](https://www.yui-rail.co.jp/common/js/layout.min.js) fetches
`/common/json/data/operation_info.json?t=<epoch ms>` with `cache: "no-store"`
and writes the current language's `text` into that element, wrapping it in a
link only when `link` is non-empty. The payload holds one `{text, link}` object
per language (`en`, `tc`, `sc`, `kr`, `jp`). It carries no status code, no
route/section field and no timestamp, so the Japanese text is the only signal.
The [manifest](yuirail_manifest.json) records source URLs, retrieval times,
original and fixture SHA-256 hashes, and extraction details.

- `yuirail_normal.json`: unmodified live response, fetched 2026-11-02 UTC.
  `現在、平常通り運行しております。`
- `yuirail_20260326033336.json`: unmodified [Wayback response](https://web.archive.org/web/20260326033336id_/https://www.yui-rail.co.jp/common/json/data/operation_info.json?t=1774489574264),
  captured 2026-03-26 03:33:36 UTC. The same normal sentence without the
  trailing `。`.
- `yuirail_20260601101306.json`: archived 2026-06-01 10:13:06 UTC. Typhoon
  No. 6 notice announcing an all-day suspension on June 1 from the first train.
- `yuirail_20260806220615.json`: archived 2026-08-06 22:06:15 UTC. Typhoon
  No. 13 notice announcing an all-day suspension on August 7.
- `yuirail_20260825141333.json`: archived 2026-08-25 14:13:33 UTC. Reports
  normal operation on August 25 and 26, with a caveat that the typhoon may
  cause suspensions or delays.

The CDX query
`https://web.archive.org/cdx/search/cdx?url=www.yui-rail.co.jp/common/json/data/operation_info.json*&output=json&collapse=digest`
returned 12 successful captures with 6 distinct digests between 2026-03-09 and
2026-09-05. All six bodies were inspected: four normal bodies (two spellings,
one of which is identical to the live text and was not copied as a separate
fixture), two all-day suspension notices, and the normal-plus-caution notice
above. Wayback stored some bodies gzip-compressed; those fixtures are the
decompressed response bodies, otherwise unmodified.

The JSON has no structured status or per-line field, so only an exact match to
the two confirmed normal sentences yields `NORMAL`. Any other text is `ALERT`
with the original text, effect `OTHER` and timing `UNKNOWN`; prose never sets
`DELAYED`, `SUSPENDED` or `PARTIAL_SUSPENSION`. The 2026-08-25 capture is the
reason a text that mentions normal operation is not promoted to `NORMAL`.
`updated_at` stays `None`, and the `link` target, delay certificates,
timetables and non-Japanese languages are not fetched.

Malformed payloads (missing `jp`, wrong types, empty text, invalid JSON) are
synthetic tests; they verify `ParseError` handling and preservation of the
previous snapshot, not source behaviour.

The canonical route `jp:operator_95b01abb482d:line_b8a42de95ac6` (ゆいレール)
is reused from Yahoo route `620/0`. Source-specific snapshots remain
independent.

The [site policy](https://www.yui-rail.co.jp/policy/) reserves copyright in all
posted information and states that unauthorised reproduction or republication
in any medium is refused; metadata records `PERMISSION_REQUIRED`. The policy
also notes that the site's information may be changed, interrupted or stopped
without notice. Both pages were reviewed on 2026-11-02 UTC.
