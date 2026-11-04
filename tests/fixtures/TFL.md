# TfL Unified API evidence

Investigation date: 2026-11-04 UTC. Method: official public JSON, Swagger and
server-rendered status HTML; no abnormal archive was retrieved. Requests used
the library's identifying User-Agent, without credentials or browser impersonation.
The files remain local under the repository's captured-content policy.
[tfl_manifest.json](tfl_manifest.json) records each original URL, UTC retrieval
time and SHA-256 of the complete decoded HTTP response bytes. No response was
projected or edited to fabricate an incident.

## Sources and observed behaviour

- [Current status API](https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line,tram/Status):
  `tfl_live_20261104.json`, 20 lines, one anonymous GET. Real observed pairs:
  10 Good Service; 6 Severe Delays; 9 Minor Delays; 3 Part Suspended;
  5 Part Closure. Bakerloo and Lioness each have delay and suspension entries;
  Central and Piccadilly each have two delay severities. Original reasons are
  preserved locally and are not reproduced here.
- A second actual Provider refresh, saved via SnapshotRecorder at 13:05:10 UTC,
  produced `tfl_live_20261104_130510.json`. Lioness changed from delay/partial
  suspension to 2 Suspended; Central changed from two delay severities to one.
  Extraction from the recorder gzip body is lossless and recorded in the manifest.
  This verifies an actual status transition, not recovery to normal.
- [Official status page](https://tfl.gov.uk/tube-dlr-overground/status/):
  `tfl_page_20261104.html`, confirming the current display and six named
  Overground lines rather than a single aggregate Overground entry.
- [Severity metadata](https://api.tfl.gov.uk/Line/Meta/Severity):
  `tfl_severity_20261104.json`, verifies the exact 0–20 code/label pairs for all
  five selected modes. Other statuses have specification-backed synthetic
  tests; severity metadata alone does not demonstrate an actual incident.
- [Swagger](https://api.tfl.gov.uk/swagger/docs/v1):
  `tfl_swagger_20261104.json`, source models and current vs date-range endpoints.
  `ValidityPeriod.isNow` identifies realtime rather than planned/information.

The live list contains current `PlannedWork` entries with `isNow=false` and
validity dates spanning the capture time. Thus false does not establish a
future notice. PlannedWork identifies work type, not duration; there is no
long-term-only field in this list. All current lineStatuses are retained.
Separate dated/future endpoints and station feeds are not requested.
`NORMAL` concerns only these line statuses, not every station or train.

## Mapping and unknowns

Mapping uses exact dedicated code/label pairs, never reason text:

| Codes | Common status | Reason |
| --- | --- | --- |
| 10, 18 | NORMAL | Good Service / No Issues |
| 6, 9 | DELAYED | Severe / Minor Delays |
| 1, 2, 16 | SUSPENDED | Closed / Suspended / Not Running |
| 3, 5, 7, 11 | PARTIAL_SUSPENSION | Part Suspended / Part Closure / Reduced Service / Part Closed |
| 0, 4, 8, 12–15, 17, 19, 20 | ALERT | Other dedicated service notices; no extra effect inferred |

Planned Closure is an advisory rather than proof of an active full suspension.
Service Closed is kept advisory: the label does not establish a disruption
rather than the end of operating hours. Unknown or mismatched pairs retain
their code, label and original reason as UNKNOWN. Multiple statuses follow
the library's existing combined_status ordering; each alert keeps its own effect.

Known non-normal alerts have ACTIVE timing only for a dedicated period with
`isNow=true`. Others stay UNKNOWN regardless of dates or wording. Each period
is a separate alert with its explicit bounds; disjoint windows are not merged.
No source status-update timestamp was confirmed; record creation/modification
and sentinel timestamps are not used as updated_at.

Synthetic tests cover all other code mappings, unknown/contradictory pairs,
negation/recovery/future prose, multiple validity windows, missing/duplicate/
unknown lines, mode changes, foreign lineId, missing/invalid fields, naive or
reversed dates, HTTP/transport failure, old-snapshot retention and recovery.
No real same-incident recovery capture was obtained.

## Operators and scope

Canonical IDs identify lines independently of concessions. Actual operators
are separate from data source TfL:

- Tube: London Underground Limited.
- Overground: First Rail London Limited. The [TfL September 2026 response](https://tfl.gov.uk/corporate/transparency/freedom-of-information/foi-request-detail?referenceId=FOI-2069-2627)
  explicitly identifies the current operator; older Arriva material is historical.
- Elizabeth line: GTS Rail Operations Limited, confirmed by the [TfL improvement page](https://tfl.gov.uk/travel-information/improvements-and-projects/improving-the-elizabeth-line?cid=elizabeth-line-improvements).
- DLR: KeolisAmey Docklands Limited; Tram: Tram Operations Limited, as described
  in [TfL's operations overview](https://tfl.gov.uk/corporate/about-tfl/what-we-do).

DLR and Tram are each a network-level GROUP. Tube and the six Overground
names remain individual lines. The API's parent line determines affected_line_ids;
alternative ticket-accepting lines mentioned in reasons are not affected lines.
Bus, river, cable car, National Rail, arrivals and station/accessibility feeds
are outside this provider's scope.

## Licence and access

[Transport Data Service terms](https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service)
permit commercial/non-commercial reuse subject to conditions. Attribution is
`Powered by TfL Open Data`; review the complete licence for OS/Geomni notices,
branding, non-endorsement and other requirements. The terms state commencement
on registration. The [API portal](https://api-portal.tfl.gov.uk/products)
separately permits anonymous access at 50 requests/minute. Technical anonymous
access does not resolve that registration clause. Metadata records this
distinction; it does not provide individual clearance. No registration, key
management or acceptance on the user's behalf was performed. Runtime uses
one anonymous request per refresh with the common 30-second default limit.
