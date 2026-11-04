# Taoyuan Metro official operating-status evidence

Investigation: public HTML/JavaScript inspection and archived official HTML.
Requests use the library's identifying User-Agent. No account or key is needed.
Exact UTC retrieval times, request/final URLs, original SHA-256 values and local
fixture hashes are in [taoyuan_metro_manifest.json](taoyuan_metro_manifest.json).
Third-party HTML and JavaScript are local only and excluded from Git/packages.

## Source and status mapping

The [official Chinese homepage](https://www.tymetro.com.tw/tymetro-new/tw/)
server-renders the latest operating status twice inside `.banner .operation`,
for desktop and mobile. Both copies have the same heading and a single status
span. We validate the two copies and require identical marker/label pairs.

| Evidence | Marker | Label | Mapping |
| --- | --- | --- | --- |
| [2024-04-03 01:21:30 UTC](https://web.archive.org/web/20240403012130id_/https://www.tymetro.com.tw/tymetro-new/tw/) | `red` | 全線停駛 | `SUSPENDED`, `NO_SERVICE` |
| [2024-04-08 10:02:45 UTC](https://web.archive.org/web/20240408100245id_/https://www.tymetro.com.tw/tymetro-new/tw/) and [2024-10-01 01:54:24 UTC](https://web.archive.org/web/20241001015424id_/https://www.tymetro.com.tw/tymetro-new/tw/) | `green` | 正常營運 | `NORMAL` |
| [2026-07-11 04:36:49 UTC](https://web.archive.org/web/20260711043649id_/https://www.tymetro.com.tw/tymetro-new/tw/) | `yellow` | 減速營運 | `ALERT`, `OTHER` |
| Live response on 2026-11-04 UTC | `green` | 正常營運 | `NORMAL` |

Reduced speed does not establish delays or reduced service frequency. Colours
alone do not classify a state. Unknown marker/label pairs remain `UNKNOWN`,
retaining both; missing/empty fields and disagreeing responsive copies fail
atomically rather than selecting whichever copy appears normal.

`/tymetro-new/js/template.js`, `/tymetro-new/js/custom.js` and
`/tymetro-new/js/web.min.js` were inspected. The clock code in `custom.js`
updates `#timereload` from the browser clock; it is not a source update time.
No additional status mapping was found in those scripts. The status labels
above are verified by HTML, not inferred from script colours or news prose.

Local HTML fixtures contain BeautifulSoup `html.parser` serialisation of
both operating panels, wrapped in `html/body/.banner`. Text, classes and icons
are unchanged; unrelated markup/news are omitted. The manifest distinguishes
original bytes from extracted fixtures. The 2024-10-01 page is supporting
evidence only and is not a test fixture.

## Scope and limitations

The Airport MRT line is represented once (`tw:tymetro:airport`), operated by
桃園大眾捷運股份有限公司. No matching canonical route existed before this addition.
The official homepage lists Airport MRT stations A1 through A22. The provider
does not split express/local service, infer affected stations or add other
planned lines. The [official route page](https://www.tymetro.com.tw/tymetro-new/tw/_pages/travel-guide/road.html)
was also inspected for route identity; it is not fetched by the provider.

Separate news, planned works/operating plans, linked articles/PDFs, timetables,
train positions and delay certificates are outside coverage. Raw HTTP
recordings still contain those page sections. `NORMAL` refers to the dedicated
status panel only. Future/long-term text appearing within that panel is kept
as an unknown label; no keyword/date filter discards it.

No incident validity intervals or source update timestamp are published in
the consumed panel. `updated_at`, `active_from` and `active_until` stay `None`.
Applicability mapping has not been independently established; all alerts keep
`timing=UNKNOWN`. The clock and article dates never supply these values.

The later normal archive verifies normal after suspension, without proving an
exact reopening time or an explicit same-incident recovery announcement.
Tests replay those real pages in order and verify that old alerts disappear.
Unknown/contradictory labels, missing/extra panels, disagreement, encoding and
HTTP/transport errors are synthetic tests. No dedicated delay or partial
suspension label has been verified. No live abnormal response was collected.

## Terms

Reviewed on 2026-11-04 UTC:
[official intellectual-property and disclaimer declaration](https://www.tymetro.com.tw/tymetro-new/tw/_pages/note/intellect.html).
It requires consent or authorisation for use of protected content outside
fair use, reserves personal/family non-profit copying and reasonable quotation,
and requests source attribution for the stated fair-use cases. No separate
reuse grant for operating-status data was found. Metadata records
`PERMISSION_REQUIRED`; this is a record of published terms, not a legal opinion.
