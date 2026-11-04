# Kaohsiung MRT/LRT operating-status evidence

Investigation: public HTML/JavaScript inspection and archived official HTML.
Exact request/final URLs, UTC retrieval times, identifying User-Agents and
original/fixture SHA-256 values are in
[kaohsiung_metro_manifest.json](kaohsiung_metro_manifest.json).
Third-party response bodies remain local and are excluded from Git/packages.
No account or API key is required.

The local Python 3.13 environment rejected the site's certificate chain with
`VERIFY_X509_STRICT`. Investigation and the live provider check used a custom
HTTPX client with that strict flag cleared, while certificate-chain and hostname
verification remained enabled. The provider does not change TLS settings.

## Source and mapping

The [official homepage](https://www.krtc.com.tw/) server-renders two copies of
the operating status: `#RtStatus` and `#RtStatusMobile`. Each has two direct
rows, identified by their visible group headings `捷運` and `輕軌`, with a
direct `.ci` marker. The labels include those headings. We require exactly
one row per group in each panel and identical marker/label/reference values
between the two panels; row order is irrelevant.

| Group | Marker classes | Entire label | Mapping |
| --- | --- | --- | --- |
| MRT red/orange | `g ci` | 捷運全線正常營運 | `NORMAL` |
| Light rail | `g ci` | 輕軌全線正常營運 | `NORMAL` |

Both pairs were observed in live HTML on 2026-11-04 UTC and
[2026-10-17 10:09:42 UTC archived HTML](https://web.archive.org/web/20261017100942id_/https://www.krtc.com.tw/).
The archive request for 2026-11-01 redirected to this exact capture; the
manifest records both URLs. Fixtures are BeautifulSoup `html.parser`
serialisations of these two panels, wrapped in `html/body`. Text and classes
are unchanged; unrelated content is omitted.

Homepage inline CSS assigns green/red/yellow colours to `g`/`r`/`y`, but does
not specify delay, suspension or partial-suspension semantics. Inline scripts
and [common.js](https://www.krtc.com.tw/scripts/common.js) were inspected;
no additional operating-status mapping was found. `layout.css` was also
inspected. These are investigation sources, not runtime request endpoints.

CDX searches covered monthly captures from 2023 through 2026 and daily
captures around 2024-10-02 through 2024-10-05 and 2025-07-06 through 2025-07-08.
The inspected 2024-10-01, 2025-07-01 and 2026-07-01 responses lack the current
status panels. News headlines in an old page do not establish a dedicated
current-status mapping. No abnormal panel was obtained. Search results do
not establish that no other abnormal capture exists.

Every other marker/label pair remains `UNKNOWN`, retaining its label and
marker classes. Additional references prevent classification as normal and
are retained as resolved URLs without fetching their bodies. Missing,
duplicate, empty or unidentifiable group rows, missing/duplicate markers,
extra rows and inconsistent panels raise `ParseError`, retaining the entire
previous snapshot. Plain news text outside these panels does not affect them.

## Scope and identity

The [official route page](https://www.krtc.com.tw/Guide/guide_map) lists red,
orange and light-rail routes. The status panels distinguish MRT from light
rail but do not distinguish the two MRT routes. The approved public API is:

| Attribute | Canonical ID | Scope |
| --- | --- | --- |
| `metro` | `tw:krtc:metro` | `GROUP`: red/orange together |
| `light_rail` | `tw:krtc:light_rail` | `LINE`: circular light rail |

No matching canonical definitions existed before this addition. Both use
operator `tw:krtc`, 高雄捷運股份有限公司, identified in the official site's
footer. The [official light-rail service regulations](https://www.krtc.com.tw/KLRT/regulations?id=af35969a3414424684137615174bcc79)
also identify the company; the corporate homepage reports both MRT and LRT
operations. Physical red/orange lines are not registered as if the source
published independent statuses. Alerts do not assert that an entire group or
every member line is affected: `affected_line_ids=()`.

Separate news/important notices, planned works, linked article bodies, PDFs,
timetables, train positions and arrival times are outside coverage. Raw HTTP
recordings still include unrelated homepage sections. `NORMAL` refers only
to the declared operating-panel scope. Future or long-term text within a
status row is retained as unknown; prose is not used to filter it out.

No source update time, incident validity interval or verified active-timing
mapping is published in the consumed rows. `updated_at`, `active_from` and
`active_until` remain `None`; `timing=UNKNOWN`. The footer update date and
fetch time are not incident timestamps. Delay, suspension, partial suspension
and explicit same-incident recovery wording remain unverified.

Tests of unverified labels/colours, contradictory pairs, future/negated text,
references, malformed panels, HTTP/transport/encoding errors and transitions
back to normal are synthetic. The real normal captures verify source shape
and normal pairs, not actual incident recovery.

## Published conditions

Reviewed on 2026-11-04 UTC: the official homepage/footer,
[privacy policy](https://www.krtc.com.tw/WebService/privates) and
[information-security policy](https://www.krtc.com.tw/WebService/security).
The footer reserves copyright. These linked policies do not provide a
service-status reuse licence or affirmative commercial reuse grant.
Metadata records `UNSPECIFIED`, without treating public access as a reuse
grant. This records the inspected published conditions, not a legal opinion.
