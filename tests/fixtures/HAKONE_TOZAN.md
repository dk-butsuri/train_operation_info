# Hakone Tozan official provider evidence

The provider consumes only the `T0001` railway item from
[Hakone Navi operation information](https://www.hakonenavi.jp/transportation/).
It covers the Odawara--Hakone-Yumoto--Gora railway, whose stations appear on
the [linked railway page](https://www.hakonenavi.jp/hakone-tozan/). This
matches the existing Yahoo `147/0` canonical line
`jp:operator_5dbad158fdda:line_a0694844624f`, operator 小田急箱根.
T0002 is a separate cable-car item and is outside this provider's scope.

## Acquisition and fixtures

Investigation used public HTML/JavaScript and Wayback's CDX index with
`filter=statuscode:200&collapse=digest`, inspecting a targeted set of captures.
`reports/investigate_hakone_tozan.py` preserves retrieved originals and UTC
retrieval times in `reports/hakone_tozan/manifest.json`. Failed requests are
recorded as failures, not evidence of the source's contents.

`reports/extract_hakone_tozan.py` serializes `.operation` with BeautifulSoup
`html.parser`, removes only the graphical `.operation_map`, and wraps the
result in UTF-8 HTML. Actual status/detail text is unchanged; other modes,
the tabs and congestion content remain to test isolation. Original and
extracted SHA-256 hashes, source/final URLs, retrieval and capture times,
extraction and raw paths are in [hakone_tozan_manifest.json](hakone_tozan_manifest.json).
Digits in `capture_utc` denote `YYYYMMDDhhmmss` in UTC, not local time.

| Fixture | Source / capture UTC | Railway and other modes |
| --- | --- | --- |
| `hakone_tozan_normal.html` | Live 2026-11-02 15:51:55.689771 UTC | Railway 平常通り運行中; cable car 運行は終了しています |
| `hakone_tozan_20230326061457.html` | [2023-03-26 06:14:57 UTC](https://web.archive.org/web/20230326061457id_/https://www.hakonenavi.jp/transportation/) | Railway and cable car normal |
| `hakone_tozan_20250321040309.html` | [2025-03-21 04:03:09 UTC](https://web.archive.org/web/20250321040309id_/https://www.hakonenavi.jp/transportation/) | Railway normal; ropeway warns of possible suspension due to strong wind |
| `hakone_tozan_20260208142500.html` | [2026-02-08 14:25:00 UTC](https://web.archive.org/web/20260208142500id_/https://www.hakonenavi.jp/transportation/) | Railway normal; ropeway sections closed for snow/maintenance, cable car business hours ended |

Earlier original-layout captures (20191019095417, 20191118050015,
20191214011408, 20200401233055, 20200716163557 at the same original URL)
are retained for investigation only. For example,
[2019-10-19 09:54:17 UTC](https://web.archive.org/web/20191019095417id_/https://www.hakonenavi.jp/transportation/)
has `li.column2-pattern2-box[data-id="4"] > .title-state` saying
運休、運転見合わせあり, and a Hakone-Yumoto--Gora closure with long recovery.
The heading does not establish total Odawara--Gora closure. The old layout
is not accepted by the current parser; no rewritten legacy incident is
presented as modern official evidence. The 2020-09-19 normal capture is
not proof of same-event recovery and also predates the current tab markup.

## Verified mappings and limits

The current `.operation_contents[data-toggle-contents="operation"]` contains
`.operation_item[data-code="T0001"]`. `data-name="箱根登山電車"` and
`data-route-cd="RT0004"` cross-check identity. The dedicated
`.operation_stateWrap > .operation_state` supplies the source status.
The exact normal label 平常通り運行中 occurs across multiple captures and live
HTML. With no further text or warning/unknown styles, it maps to `NORMAL`.
The source name 箱根登山電車 is retained as `source_line_names`.

The same common item/heading markup on ropeway items verifies
`operation_item-error` with `operation_state-error` as generic warnings.
In 2025 this can mean only possible suspension; in 2026 it combines actual
snow closure and scheduled maintenance in different sections. Consequently
the warning pair maps only to `ALERT`, effect `OTHER`, without inferring
full/partial suspension, delay or timing. Applying this common styling to
T0001 is covered by explicitly synthetic tests; **no modern abnormal railway
response was obtained**. Unknown styles, an inconsistent warning pair,
unrecognized labels without warning styling, or normal plus extra notice
map to `UNKNOWN`, with all item text retained. Normal with warning styling
also remains `UNKNOWN`.

The business-hours completion label is verified on other modes, not a
railway incident, and remains `UNKNOWN`; it never maps to `SUSPENDED`.
Section titles, statuses, cause labels/values, captions and notes remain in
the description. Narrative keywords, dates and route names do not assign
additional semantics. Warning text does not imply the entire route is closed.
An alert is attached only to the canonical railway item, not other modes.

No dedicated update/applicability/active-period fields were verified.
`data-debug` is an operation-panel generation/debug value, not a labelled
notice update: it is not used for `updated_at`. `updated_at=None`,
`timing=UNKNOWN`, `active_from=None`, `active_until=None` throughout.
Long-term text within the item is retained without inferring duration;
separate news/planned changes, global advisories, linked articles,
congestion, positions, delay certificates and all other modes are unparsed.
Those excluded parts can still occur in the raw recorded response. Normal
is a statement only about the declared parsed scope.

The reviewed [public script](https://www.hakonenavi.jp/assets/js/script.js?v=1784599900)
toggles `.operation_item_toggle`; its POST to `/_include/json_operation.php`
drives the global summary (`is_alert`, `name`), with no per-line attribution.
That endpoint is deliberately not used to classify railway service. Runtime
requires one HTML GET, declared in metadata. The recorder and replay tests
verify that exact request and state; a mock recording is not new live evidence.

Missing/duplicate panels, railway items or status fields, empty statuses,
changed identity, HTTP/transport failures preserve the prior snapshot.
Normal fixtures test other-mode isolation; synthetic warning-to-real-normal
transitions test clearing old alerts, not real incident recovery. Modern
railway abnormal layouts/labels, delays, same-event recovery and comprehensive
standalone planned/long-term notices remain unverified.

## Terms

The [site policy](https://www.hakonenavi.jp/policy/) was retrieved at
2026-11-02 15:51:55.396318 UTC. Sections 2 and 4 restrict unauthorized
reproduction/modification of site contents while reserving statutory private
use/quotation and requiring attribution for quotations. No commercial reuse
grant was found. Metadata uses `PERMISSION_REQUIRED`, the policy URL and
this fixed review timestamp. The live service panel's general timetable
advisory does not grant reuse permission or prove any specific railway delay.
