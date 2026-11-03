# DB Verkehrslage / DB Fernverkehr

Investigation on 2026-11-03 UTC used public HTML and JavaScript reverse
engineering and live abnormal JSON. No archived abnormal or recovery response
was used. Original URLs, retrieval/write-completion timestamps, raw SHA-256,
fixture SHA-256 and exact projection rules are in [db_manifest.json](db_manifest.json).

The human-facing [official Fernverkehr listing](https://verkehrslage.bahnhof.de/de/region/DB_Fernverkehr)
is linked through the redirect from bahn.de/aktuell. Its initial server-rendered
zero count has `isLoading=true` and `hasLoadedAllDisruptions=false`; this is not
evidence of normal operation. The provider never reads that count.

The public Nuxt configuration supplies the same-origin `risApiUrl` and public
`risApiKey`. The latter is read afresh at runtime, never hard-coded. The page
fixture retains only the two configuration properties, with a dummy public
key; unrelated configuration is omitted. The parser does not execute JavaScript.

`CVs5M6ee.js` defines the public API client, `/api/views/disruptions` pagination
and `/api/views/message` lookup. `Dhqahhbt.js` calls the listing with
`channels=AwarenessBlitzbox,TrafficReport` and
`organisationalUnitNames=DB_Fernverkehr`, and generates current-day bounds in
`Europe/Berlin`. The provider uses that same listing scope, narrowed to the
current local date, and requests all offset pages. Live response `total=72`
contained 70 objects: `total` bounds pagination offsets and is not a returned
object-count invariant. Different totals during a multipage refresh, duplicate
communication IDs, wrong offsets/limits, or an ignored organisation/channel
filter fail the refresh atomically. Server-side suppression means a short page
alone cannot stop pagination.

The first response's reference time is used consistently for the local-date
query, expiry decisions and `fetched_at`. Recording/replay therefore uses the
same date/expiry boundary even if the remaining requests cross midnight or a
communication expires while fetching. Fixture tests pin this time to
2026-11-03T03:40:00Z; they do not depend on the test machine's date.

The official disruption/construction selector compares the dedicated
`disruption.cause` to `CONSTRUCTION`. These objects are excluded from output,
while raw HTTP recording still contains them. Only the shared identity,
parent/cause and expiry envelope is validated for construction objects; their
effect, organisation hints and detail body are outside interpretation and
are not validated. The saved list contains 66
construction and four technical-problem communications. Parent/child pairs
have separate IDs and are retained separately. Their two distinct full German
texts were fetched from all four message endpoints; each pair was byte-identical.
The fixture stores one copy per identical pair. The provider retains caption,
summary and communication body, converting HTML body to readable text.

The API's organisational unit is a **group** (`de:db_fernverkehr:network`), not
an affected physical line. No German railway lines were previously registered.
The group remains `UNKNOWN` when reports exist. Every report has
`effect=OTHER`, `affected_line_ids=()`, `language=de`, `timing=UNKNOWN`, and no
incident validity period. Dedicated effects such as `NO_SERVICE` can refer to
a station, individual trains or an affected section: they are preserved in
`source_status` and never promoted to a whole-network service interruption.
Text mentioning delay, suspension, reopening or future dates is not classified.

`communication.end` and `disruption.end` are dedicated expiry fields; the
official `ks()` filter omits objects after either timestamp. This permits
discarding an expired report but does not prove that a retained report is
currently active. Official `As()` also removes a child whose immediate parent
is missing or fails `ks()`. The fixture retains `parent` IDs; the provider
matches this behaviour, while standalone communications need no parent.
The parent's common expiry envelope is relevant even when its construction
content is outside output scope. Repeating intervals and publication/communication timestamps
are not converted into `active_from`, `active_until`, `ACTIVE`, or `updated_at`.

An empty, fully fetched non-construction/non-expired listing yields `NORMAL`
only within the declared current-day organisational listing. It does not
assert punctuality, absence of small/train-specific disruptions, absence of
construction, or anything about DB Regio/S-Bahn. Empty lists, clearing/recovery,
new causes/effects, malformed structures and pagination are synthetic test
cases; the real live fixture is abnormal. The tests cannot establish source
format stability for unseen responses.

The [DB InfraGO terms](https://verkehrslage.bahnhof.de/de/impressum), reviewed
on 2026-11-03 UTC, restrict uses to displaying/checking information and supplied
functions; other uses require prior written consent. Commercial processing,
copying and republication, including automated extraction, require consent.
Metadata records `PERMISSION_REQUIRED`; public website access is not a reuse
licence. No separate open-data licence was found on this listing.
