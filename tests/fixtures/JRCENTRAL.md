# JR Central official conventional-line evidence

Investigation: public HTML/JavaScript reverse engineering and live official
JSON/history responses. No Wayback archive was used.
[jrcentral_manifest.json](jrcentral_manifest.json) records exact URLs, UTC
retrieval times, original SHA-256 and fixture SHA-256. All fixtures contain
unmodified HTTP response bytes; the operation/history JSON includes a UTF-8
BOM, removed only when decoding for Pydantic validation. Downloads used httpx.

The source page is https://traininfo.jr-central.co.jp/zairaisen/index.html.
Its public `js/contents.js` defines these relative data endpoints:

- `data/hp_service_jotai_kanri.json`: service gate.
- `data/trainInfo/json/unkou.json`: current events and delivery messages.
- `data/trainInfo/history/{outNo}/unkou.json`: publicly linked history format.
- `data/hp_senku_master_ja.json`: route names, sections and panel categories.
- `data/locales/ja/hp_koteimoji_master.json`: dedicated Japanese labels/FAQ.

Runtime consumes only the service gate and current operation JSON. The other
files are investigation evidence, not runtime endpoints. Static route bindings
cover the 13 entries whose `senkuKbn` is `1`. Twelve reuse existing Yahoo
canonical IDs. Chuo covers Nagoya--Shiojiri, so it receives a new ID instead of
reusing either Nagoya--Nakatsugawa or Nakatsugawa--Shiojiri. This distinction
prevents a broad official notice from being assigned to one arbitrary section.

`status.js:resolveLineInfoStatusText` uses `event.status_id` and the locale's
`line_info_status` table. The mapping is:

| Dedicated code | Official detailed label | Common status |
| --- | --- | --- |
| 0001--0004 | 運転見合わせ | SUSPENDED |
| 0005 | 遅れ・運休あり | ALERT |
| 0006 | 遅れあり | DELAYED |
| 0007 | 運休あり | ALERT |
| 0009 | 平常運転 | NORMAL |
| Other | Original `status[].name` retained | UNKNOWN |

The top panel's broader `遅れ／運休あり` cannot distinguish delays from
cancellations. The detailed code 0006 can. Code 0007 only establishes that
cancellations exist, not whether all/some services are cancelled. Neither it
nor 0005 is converted into a full or partial suspension. Prose is not parsed
to add a more specific effect. Suspension status refers to the reported
affected section, not a guarantee that the entire canonical line is closed.

`train_information.js` filters `events` by `imp_line` and `message_info` by
`trainline`, then pairs their per-route arrays by index; the provider does the
same and rejects mismatched counts. It uses Japanese names, never foreign
translations. Duplicate event numbers, unknown route names, missing Japanese
fields, bad types and normal flags contradicting nonempty incident lists fail
atomically. `common.js:isOutOfService` hides the usual UI whenever
`serviceJotai != '0'`; the provider rejects that response before consuming
possibly stale operation data. The two requests are sequential, as a failed
maintenance gate must prevent publishing normal state from old data.

The saved live response (ono 60742) and histories 60739, 60740 and 60741 verify
actual 0006 delay events. A subsequent live capture (ono 60744,
`jrcentral_normal.json`) has `check=0` and both `events` and `message_info`
explicitly null. It verifies clearing the previously published delay and all
old alerts. The Japanese page generates a normal route panel when no events
match; `check=0` is the explicit all-normal display branch. Null arrays are
accepted only for that branch; missing fields still fail. Actual suspension
and cancellation responses were not obtained. Tests for those states, unknown
codes, malformed inputs, disabled-provider behavior and HTTP failure are
explicitly synthetic. They verify implementation, not source semantics.

`create_time` is a date, and the header's update display derives from HTTP or
current time. Neither is used as a source update timestamp: `updated_at=None`.
No dedicated event applicability/validity fields were verified. `timing` stays
UNKNOWN, and `active_from`/`active_until` stay None, including for delay and
suspension codes. Recovery/expiry is represented only by removal/replacement
of source events, not by text/date heuristics.

Scope excludes express/liner panels (`senkuKbn=3/4`), separate
`data/notice/json/oshirase.json` notices, transfers, recovery/supplement images,
linked PDFs, delay certificates, train positions and timetables. Narratives
inside the consumed `message_info` remain verbatim, even if they discuss
plans or long closures. There is no duration/forecast filter. Normal means no
reported event in this scope, not absence of all delays or separate notices.
The FAQ says notices concern roughly ten-minute delays or anticipated delays;
02:00--04:00 updates may be unreliable or unavailable.

Shinkansen investigation: the public
https://traininfo.jr-central.co.jp/shinkansen/pc/ja/index.html loads
`../../common/js/main.js` and `index.js`. Their derived
`shinkansen/var/train_info/service_status.json` and `ti01_ja.json` URLs redirected
to https://jr-central.co.jp/ during this review, including timestamped requests.
The corporate homepage's `/_assets/_config/config.js` points to
https://traininfo.jr-central.co.jp/shinkansen/service-info/_api/shinkansen.json,
which returned `{"shinkansen":{}}`. The homepage's `/_javascript/index.js`
requires `flag` and `comment`, so this empty object is not normal-operation
evidence. No Shinkansen route is included or falsely reported as normal.

Terms reviewed at the recorded policy retrieval time:
https://jr-central.co.jp/policy/ and the source FAQ at
https://traininfo.jr-central.co.jp/zairaisen/faq.html (text from Japanese locale).
The general policy reserves copyright and prohibits unapproved reuse except
for legally permitted cases; the service FAQ separately prohibits unauthorized
reproduction/copying. Metadata uses PERMISSION_REQUIRED, retaining the
statutory exception, and does not imply that technical access grants a licence.
