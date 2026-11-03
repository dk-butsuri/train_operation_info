# Rinkai Line evidence

Reviewed on 2026-11-02 UTC. The provider reads the Japanese
[official service page](https://service.twr.co.jp/rinkai/public/information?lang=ja)
and only its `#serviceInfo` notice. The legacy
`https://service.twr.co.jp/service_info/information.html` redirects there.
The homepage's `/service_info/top.js` redirects to `/rinkai/public/top?lang=ja`
and writes a notice anchor; it provides no status-code mapping. The service
page contains no script-driven status feed. Its CSS styles the notice.

## Official fixtures

| Fixture | Source/capture (UTC) | Observed content |
| --- | --- | --- |
| `rinkai_normal.html` | Live, 2026-11-02 05:52:14.809157 UTC | Exact normal text, no update date |
| `rinkai_20180122093824.html` | [2018-01-22 09:38:24](https://web.archive.org/web/20180122093824id_/http://service.twr.co.jp/service_info/information.html) | Snow, delays and JR through-service cancellation; update 17:23 JST |
| `rinkai_20180904125255.html` | [2018-09-04 12:52:55](https://web.archive.org/web/20180904125255id_/http://service.twr.co.jp/service_info/information.html) | Obstruction, delays and turnback; update 19:42 JST |
| `rinkai_20191012171221.html` | [2019-10-12 17:12:21](https://web.archive.org/web/20191012171221id_/https://service.twr.co.jp/service_info/information.html) | Typhoon suspension and conditional next-day reopening; update 14:31 JST |
| `rinkai_20220825002322.html` | [2022-08-25 00:23:22](https://web.archive.org/web/20220825002322id_/https://service.twr.co.jp/rinkai/public/information?lang=ja) | JR abnormal-noise investigation causing delays; update 08:15 JST |
| `rinkai_20220825005348.html` | [2022-08-25 00:53:48](https://web.archive.org/web/20220825005348id_/https://service.twr.co.jp/rinkai/public/information?lang=ja) | Normal after preceding delay capture; no update date |
| `rinkai_20220926105254.html` | [2022-09-26 10:52:54](https://web.archive.org/web/20220926105254id_/https://service.twr.co.jp/rinkai/public/information?lang=ja) | JR through-service cancellation, Rinkai turnback and alternative transport; update 18:51 JST |

`reports/extract_rinkai.py` serializes the complete `.contBody` with
BeautifulSoup's `html.parser`, wrapped with a UTF-8 declaration. Original
2018/2019 HTML declares Shift_JIS; newer pages declare UTF-8. Status text is
not rewritten. Fixtures retain the header, page clock, policy and notice,
including the source's nested paragraph markup. [rinkai_manifest.json](rinkai_manifest.json)
records original and extracted SHA-256 hashes, source/final replay URLs, UTC
capture and retrieval times, processing and original file paths. It also
records investigated captures not selected as fixtures, scripts and CSS.
All seven fixture contents are real official responses. Additional malformed,
contradictory and unknown-content tests are explicitly synthetic.

CDX indexes were queried for the old URL and the current prefix with
`filter=statuscode:200&collapse=digest`. Selected captures cover snow, typhoon,
recent-format delays, through-service cancellation and normal operation.
This is a targeted sample, not an exhaustive inspection of every capture.
The normal capture after the August delay tests clearing, but its text does
not explicitly identify the previous incident as resolved. Current abnormal
HTML, long-term closure and standalone partial closure remain unverified.

## Normalization and scope

The only machine-distinguishable status in the retrieved content is the
complete verified normal sentence. Other notices are prose, with no separate
status code or status heading, so they yield `ALERT` and preserve the original
text. Narrative occurrences of delay, suspension, prior disruption or future
plans do not determine `DELAYED`/`SUSPENDED`/`PARTIAL_SUSPENSION`. A mixed normal
sentence and extra notice yields `UNKNOWN` while keeping the entire notice.
JR through-service cancellation does not imply suspension within Osaki--Shin-kiba.
Use `affected_lines` / `alerts`, rather than `delay_lines`, for these notices.

`p.date` explicitly labels a full Japanese date/time as 更新; it becomes
`updated_at` with `Asia/Tokyo`. The separate `#nowTime` advanced from 14:51 to
14:52 between live requests while the normal notice was unchanged; it is a
page clock. A normal response has `updated_at=None`. Fixture tests verify
the 2022 delay's update is 08:15, rather than the page clock's 09:23.

No dedicated duration/applicability fields exist. The typhoon notice includes
current service and conditional tomorrow service in one message. Unstructured
or yearless prose cannot establish a precise period. `timing` remains `UNKNOWN`; `active_from` and `active_until` remain unset.
Missing/empty/duplicated required panels and malformed explicit dates fail
atomically, retaining the previous snapshot. A later normal capture clears
the alert and its previous update time. Snapshot recording/replay is covered
by `tests/test_snapshots.py` using the real 2022 delay fixture via MockTransport;
that recording is not additional live evidence.

Publication criteria include delays of 30 minutes or more (also anticipated),
JR through-service cancellation with turnback within the Rinkai line, suspended
operation and other information as needed. The page warns that its notice may
differ from actual service. Separate homepage news/linked planned changes,
positions, delay certificates and X are not fetched; normal in this panel does
not prove their absence. The existing Yahoo canonical route and operator are
reused with independent provider snapshots.

## Terms review

The reviewed homepage/navigation and service page did not expose general
website reuse terms or a reuse licence for the service HTML. The homepage
reserves copyright. The service page's link to
[social media terms](https://www.twr.co.jp/about/tabid/197/Default.aspx)
was reviewed at 2026-11-02 05:52:15.263408 UTC. Article 1 scopes those terms to
official accounts and associated services; article 2 requires written consent
for reuse of their content. That is not evidence of permission for this HTML
feed. Metadata therefore uses `terms_url=None`, records the service/social
media URLs in `additional_terms_urls`, and classifies HTML reuse as
`UNSPECIFIED`, with this scope distinction in `usage_note`. No commercial grant
was found; the classification does not imply unrestricted reuse.
