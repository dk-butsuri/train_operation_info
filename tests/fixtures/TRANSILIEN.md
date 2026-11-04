# Transilien: SNCF route groups and RATP Paris Métro

Investigated on 2026-11-03 UTC by inspecting official public HTML, JavaScript,
current JSON including abnormal notices, and published terms. No archived
abnormal capture is claimed. The exact request URLs, UTC retrieval times,
SHA-256 of each complete original response, and transformations are recorded in
[transilien_manifest.json](transilien_manifest.json). The Métro extension was
investigated on 2026-11-04 UTC using the same official public API and bundle;
its independent capture records are in
[transilien_metro_manifest.json](transilien_metro_manifest.json).

## Scope and route identities

The [official home page](https://www.transilien.com/fr/#traffic-info-app)
mounts `#traffic-info-app` and loads the
[public traffic component](https://www.transilien.com/tricharte/js/component-traffic-info.bundle.js?v=52612).
[transilien_home.html](transilien_home.html) preserves this mount point and
script reference. [transilien_public_script.js](transilien_public_script.js)
contains noncontiguous, otherwise unmodified excerpts of that bundle around
API calls, severity/display mappings and current/future availability checks.
Comments separate the excerpts; they are evidence, not an executable fixture.

The component requests the
[summary](https://www.transilien.com/api/traffic/infos) and
`https://www.transilien.com/api/traffic/line/{code}?lang=fr` for a selected route.
Supported SNCF source codes are `RER_C`, `RER_D`, `RER_E`, and
`LIGNE_H/J/K/L/N/P/R/U/V`. They map directly to the canonical SNCF route-group
IDs `fr:sncf:rer_c/d/e` and `fr:sncf:ligne_h/j/k/l/n/p/r/u/v`.
Each is a passenger service system encompassing its routes/branches, rather
than a single physical track segment; therefore canonical scope is `GROUP`.
For example, the official [line N page](https://www.transilien.com/fr/page-lignes/ligne-n)
and line-N JSON concern the Paris Montparnasse service group, with distinct
Rambouillet, Dreux and Plaisir notices. Mapping a notice to this group does not
assert that every branch, direction or station is affected.

These twelve route groups have operator SNCF Voyageurs. In addition, the
sixteen Paris Métro lines have source codes `METRO_1` through `METRO_14`,
`METRO_3BIS` and `METRO_7BIS`, summary `mode=METRO`, and operator RATP.
Their canonical IDs are `fr:ratp:metro_1` through `fr:ratp:metro_14`,
`fr:ratp:metro_3bis` and `fr:ratp:metro_7bis`; canonical scope is `LINE`.
The source identifies a line, not the extent or affected stations of a notice.
The static provider mapping keeps the source codes and canonical IDs explicit.
The same summary and detail endpoints are used for both operators.

RER A/B have joint operation and remain excluded. Trams, buses, Orlyval,
CDGVAL and the funicular are also excluded, even when the source groups an
entry under `mode=METRO`. No route is selected merely by that mode.
One direct exploratory request to the RATP website using the repository's
User-Agent returned HTTP 403. This implementation uses Transilien's existing
independent source and does not access or bypass the RATP website.
This is **not nationwide SNCF support**: TGV, TER and Intercites are outside
the provider. The public nationwide SNCF Voyageurs and SNCF Connect pages
returned HTTP 403 when inspected directly; no speculative parser is supplied
for those blocked inputs.

## Fields and semantics

All JSON captures in both manifests are complete, unmodified HTTP responses. They
contain out-of-scope future and engineering-work content because that content
shares the same HTTP response. Parsing is restricted to the following fields.

| Official field or code | Library meaning |
| --- | --- |
| Summary `code`, `id`, `mode` | Exact static route identity; missing or duplicate supported routes fail atomically |
| Summary `fetchStatus=FULL` | Required for each supported group; other/unknown retrieval states fail, never establish normality |
| Detail `currentDisruptions` | The selected current-notice list; missing, null or non-array is a parse failure |
| Current notice `category=TRAVAUX` | Structurally excluded engineering-work category; only its discriminator is needed |
| `futureDisruptions`, `weeklyFutureDisruptions`, `monthlyFutureDisruptions` | Entirely excluded and not validated |
| `category=TRAFIC`, `severity=SLOWED_TRAFFIC/HIGHLY_SLOWED_TRAFFIC` | `DELAYED`, based on explicit slowed-traffic icon labels in the bundle |
| `category=TRAFIC`, `severity=DISRUPTED_TRAFFIC/INTERRUPTED_TRAFFIC/NOT_SERVED_STOP/NOT_SERVED_STOPS/HIGH_AFFLUENCE/UNKNOWN` | `ALERT`: a notice is established; no full-line suspension or precise impact extent is inferred |
| New category or severity | `UNKNOWN` with its original title and description |
| `modifiedDate` | Latest included notice update time, validated as timezone-aware; never its effective start |
| `broadcastStartDate` | Publication date, ignored for validity and update-time purposes |

The official bundle displays the selected line's `currentDisruptions` separately
from future notices and treats missing current retrieval as unavailable
(`MISSING_CURRENT`). The detail JSON itself has only the four notice lists and
does not include a route identity or retrieval-status field. Identity therefore
comes from the fixed request URL and the complete summary's code/id/mode.

`timing` remains `UNKNOWN` for every included notice. Membership in the
current display does not establish a continuous incident validity interval;
the saved notices include bus-night information and broad date ranges.
`active_from` and `active_until` remain `None`. HTML descriptions are decoded to
visible text with link targets retained. Body words, dates and named stations
never determine status, validity, exclusion or affected route identity.

`NORMAL` means no notice within the declared current non-works scope, and does
not mean there are no engineering works, future restrictions or nationwide
SNCF disruptions. Separate engineering works and future lists are excluded.
Long-lasting restrictions mixed into `TRAFIC` are retained: the real RER D
fixture explicitly contains reduced service for several months alongside
individual train cancellations. No prose-based duration filter is used.

## What was actually observed and what is synthetic

The twelve saved line responses contain six included current notices in total:
RER C one, RER D four and RER E one, all `TRAFIC` with literal severity
`UNKNOWN`. RER D includes both long-lasting timetable changes and same-day
cancellations. Lines L/R contain current `TRAVAUX` records; line N has future
engineering work. The other selected routes have empty current traffic scope.
All twelve summary entries are `FULL` in the saved summary. These SNCF samples
were captured on 2026-11-03 and were not replaced by the Métro investigation.

On 2026-11-04, all sixteen Métro detail requests returned HTTP 200. The separate
`transilien_metro_summary.json` capture identifies every supported Métro route
as `FULL`. Métro 6 contains one current `TRAFIC` / `SLOWED_TRAFFIC` notice,
providing a real abnormal response for the existing `DELAYED` mapping.
Its `modifiedDate` is `2026-11-04T12:32:54.000Z`; this is an update timestamp,
not an effective start. Métro 8 has a current `TRAVAUX` notice, excluded from
the parsed snapshot. Métro 6/7bis/12/13 also illustrate out-of-scope future
lists. Other Métro lines have no included current traffic notice.
The complete official bundle, home page and terms page were fetched again;
all URLs, UTC retrieval times and SHA-256 hashes are in the Métro manifest.

The combined fixture test and HTTP recording/replay use the SNCF details from
November 3 and Métro summary/details from November 4. This is an offline
composition of real captures, not a claim of a single simultaneous live
snapshot or an observed recovery transition.

Dedicated severity mappings other than the observed Métro `SLOWED_TRAFFIC`
and SNCF literal `UNKNOWN` are supported by the official JavaScript
display code, **not an archived abnormal response**. Their input tests are
synthetic. Empty-list recovery, a malformed last route retaining the whole
previous snapshot, incomplete summaries, unknown codes/categories, ignored
out-of-scope broken fields, duplicate notices, naive timestamps and narrative
counterexamples are also synthetic. No claim is made to have observed a
same-incident recovery transition in live or archived data.

All 28 routes update atomically after 29 requests. Synthetic missing,
duplicated, mismatched or incomplete Métro summary entries fail before any
detail request. A malformed SNCF or final Métro response retains the whole
previous snapshot. A synthetic Métro HTTP failure also retains the old SNCF
state even when an earlier SNCF response in the same refresh has changed.
Synthetic recovery clears the prior Métro notice. Public attribute/canonical
identity tests and synthetic state tests run without third-party captures;
recorded-response and replay tests require the local, uncommitted captures.

## Published reuse conditions

The [official conditions](https://www.transilien.com/fr/page-editoriale/conditions-generales-dutilisation)
identify SNCF Voyageurs as site publisher and reserve intellectual-property
rights in the website structure and content, requiring prior express
authorization for reproduction or representation. The extracted relevant
paragraph is [transilien_terms.txt](transilien_terms.txt); the manifest records
both original and extraction hashes. The complete November 4 terms HTML is
`transilien_metro_terms.html` in the Métro manifest and independently supports
the intellectual-property classification. No separate public traffic-API reuse grant
was located. Metadata therefore records `PERMISSION_REQUIRED`, without
equating unauthenticated access with authorization to republish.
