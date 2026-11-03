# Meitetsu evidence

Investigated 2026-11-02 UTC (2026-11-03 JST). The provider requests the
[official Japanese service page](https://top.meitetsu.co.jp/em/) using GET.
HTTP redirects, when supplied, are followed by the owned client. Disrupted
official pages have been published at `/em/ryokaku/format3.html`; that path
returns HTTP 404 during the reviewed normal live state. It is not polled
independently, because an older incident must not replace the current root page.
A contemporary live disruption and its redirect have not been observed.

## Saved official responses

| Fixture | Official source / UTC capture | Observed content |
| --- | --- | --- |
| `meitetsu_normal.html` | Live `/em/`, 2026-11-02 15:38:30.197132 UTC | Normal sentence; empty generated clock |
| `meitetsu_20230816075632.html` | [2023-08-16 07:56:32](https://web.archive.org/web/20230816075632id_/https://top.meitetsu.co.jp/em/) | Normal page after the separate typhoon capture; no explicit same-event resolution |
| `meitetsu_20230815094730.html` | [2023-08-15 09:47:30](https://web.archive.org/web/20230815094730id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html) | All 19 source route names in the mixed category; restart and next-day prose |
| `meitetsu_20240831065722.html` | [2024-08-31 06:57:22](https://web.archive.org/web/20240831065722id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html) | Two suspension blocks, mixed category, free-text predicted closures |
| `meitetsu_20260208081057.html` | [2026-02-08 08:10:57](https://web.archive.org/web/20260208081057id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html) | Hiromi suspension, mixed disruption, alternative transport on JR |
| `meitetsu_20260908095207.html` | [2026-09-08 09:52:07](https://web.archive.org/web/20260908095207id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html) | Multi-route suspension, mixed disruption, prose describing earlier restarts |
| `meitetsu_20220918035311.html` | [2022-09-18 03:53:11](https://web.archive.org/web/20220918035311id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html) | Current mixed disruption plus separate next-day typhoon prediction |

[meitetsu_manifest.json](meitetsu_manifest.json) records original response URLs,
final replay URLs, retrieval timestamps, archive captures, SHA-256 hashes,
fixture hashes and processing. It includes reviewed but unselected responses and
failed research requests; neither a CDX entry nor a successful HTTP 200 alone
proves a service response. For example, the June 2023 format3 capture is a soft
404, and is not used as service evidence. CDX searches were targeted samples,
not an exhaustive examination of all incidents.

`reports/extract_meitetsu.py` uses BeautifulSoup `html.parser` to serialize
`#wrapHeader` and `#wrapContents`, excluding the map and bottom navigation, with
a UTF-8 wrapper. Service labels, rows, route names and prose are not rewritten.
Some originals contain both UTF-8 and Shift_JIS declarations; their first
UTF-8 declaration matches the saved response. All seven HTML fixtures contain
official text, rather than constructed incidents. Source CSS and inline script
excerpts are also retained, with their processing/hashes in the manifest.

## Classification and boundaries

The official [CSS](https://top.meitetsu.co.jp/em/css/basic.css?20211001)
comments define `emLv01` as suspension, `emLv02` as delays / partial cancellation,
`emLv03` as alternative transport, `emLv04` as bus substitution, and `emLv05` as
other notices. Archived dedicated headings agree with levels 01 and 02.
Level 01 plus the complete heading `運転見合せ` yields `SUSPENDED` for the listed
sections, without assuming a whole canonical line is closed. Level 02 plus
`遅延・一部運休` yields `ALERT` / `OTHER`; it cannot distinguish delay-only from
partial cancellation. Separate delay-only/partial-only labels are unverified.
Unknown classes/headings retain their original detail as `UNKNOWN`.

Only `路線` (`ul.emListLine > li`) and `区間` (`ul.emListCmn > li`) in these
blocks determine targets. Section items consist of an exact source route name,
whitespace and station interval, as confirmed across the saved pages. The
entire interval remains in the alert. Reason rows, station names, other operators
and free prose do not supply targets. The 19 verified source names map statically
to 16 existing Yahoo canonical units; the paired Tokoname/Airport, Kowa/Chita
and Tsushima/Bisai names share IDs. This provider does not change the catalog or
split those units. `source_line_names` records the source names for each unit.

Complete known service blocks permit otherwise unlisted routes to be `NORMAL`
within this main-panel scope (`source_status=掲載なし`). Unknown targets or
free `.wrapFree` prose remain unscoped alerts. They make otherwise unclassified
routes `UNKNOWN`, while preserving verified route-specific states. The 2024
Gamagori prediction therefore does not become a current Gamagori suspension.
The all-route 2023 restart prose does not erase the dedicated mixed category.
Known blocks duplicated for different sections are combined, retaining all alerts.

The [normal page](https://top.meitetsu.co.jp/em/) inline `loadDateTimeDisp`
uses `Date.now()` and replaces `#descriptionText` outside its stated service
window of 05:00--00:30 JST. The implementation reproduces its hour/minute
condition (including 00:30:59), with the snapshot retrieval time / replay clock,
returning `UNKNOWN` with the official unavailable message and no invented incident.
That is not evidence that trains have stopped running. The displayed clock is
not an update timestamp. Abnormal script `createDate` is not documented as a
publication/update field either, so `updated_at=None` throughout.

No dedicated incident applicability/validity fields were established; all
alerts use `timing=UNKNOWN`, `active_from=None`, `active_until=None`. Dates in
predictions and restart prose are not converted to active periods.

Runtime imports only the main `.layEm` service blocks and free notices. It
excludes replacement/bus transport blocks, SVG maps, train positions, delay
certificates, linked articles and the separate top-level important notices
injected from `/tokudashi/tokudashi.html` by
[/em/js/tokudashi.js](https://top.meitetsu.co.jp/em/js/tokudashi.js).
The important-notice response was empty when inspected. `NORMAL` does not
claim that these outside-scope notices, longer-term changes or smaller delays
are absent. The [service conditions](https://top.meitetsu.co.jp/em/train_notice.html)
state a publication threshold of roughly 15 minutes affecting multiple trains,
including anticipated disruption.

## Validation and terms

Tests use saved responses through MockTransport and direct parsing. Redirects,
clock boundaries, unknown codes/targets, broken structures, connection failures
and abnormal-to-normal transitions are explicitly synthetic scenarios. The
normal archive is chronological evidence, not a verified same-event recovery.
Snapshot recording/replay of a disruption fixture and a synthetic redirect do
not constitute extra live observations. Empty/missing/duplicate required
structures fail atomically and preserve the previous snapshot.

The [general site policy](https://www.meitetsu.co.jp/site_policy/index.html)
was retrieved at 2026-11-02 15:38:31.538184 UTC. It explicitly covers top.meitetsu
and www.meitetsu content; section 2 restricts copying, secondary use, processing
and transmission. The service conditions contain a threshold/disclaimer, not
a reuse licence. Metadata records both URLs and `PERMISSION_REQUIRED`; no
commercial reuse grant was established.
