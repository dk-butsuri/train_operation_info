# JR East official service alert evidence

Investigation: public HTML/JavaScript reverse engineering; no archive replay.
The following pages were downloaded with `httpx.get` on 2026-11-02 UTC:

| Fixture | Original URL |
| --- | --- |
| `jreast_kanto_20261102.html` | https://traininfo.jreast.co.jp/train_info/kanto.aspx |
| `jreast_tohoku_20261102.html` | https://traininfo.jreast.co.jp/train_info/tohoku.aspx |
| `jreast_shinetsu_20261102.html` | https://traininfo.jreast.co.jp/train_info/shinetsu.aspx |
| `jreast_shinkansen_20261102.html` | https://traininfo.jreast.co.jp/train_info/shinkansen.aspx |

[jreast_manifest.json](jreast_manifest.json) records each exact UTC fetch time,
the SHA-256 of the downloaded response bytes and the SHA-256 of the fixture.
Fixtures contain BeautifulSoup `html.parser` serialization of `.c-heading-lv3`
and `.traininfo-routes__table` elements, wrapped in `<html><body>`. No route
labels, incident statements or status classes were changed. Script, unrelated
navigation, editorial notices, separate train cancellation lists and page
footers were omitted. Repeated rows are preserved. The four pages have
61/36/20/5 rows and 45/31/14/5 distinct source route IDs, respectively;
cross-region duplicates merge into 86 canonical entries.

Current row evidence verifies:

- `normal` + `平常運転`: normal (including all five Shinkansen entries).
- `delay` + `遅延`: delayed (e.g. Yokosuka).
- `delay` + `一部運休`: partial suspension (e.g. Ou, Uchibo, Koumi).
- `adjust` + `運転見合わせ`: suspension (e.g. Ishinomaki, Kitakami, Koumi).
- `adjust` + nested `１２時１０分頃` / `運転再開見込`: still suspended (Joban).
- `info` + `お知らせ`: notice, including planned works and long-term closures.

Labels and classes are checked together. `delay` alone does not distinguish
delay from partial cancellation. Prose mentioning suspension or reopening
does not change the current label's classification. All original notices are
retained, including multiple current statements for one route. Exact duplicate
alerts are collapsed. A normal entry from another region cannot erase an
incident. Timed labels retain their displayed estimate; it is not an update or
incident validity timestamp. The region's `現在` clock is not the detail page's
`配信` time, so `updated_at=None` for these snapshots.

Inspected scripts:
https://traininfo.jreast.co.jp/train_info/js/getinformation-jp-kanto.js and
https://traininfo.jreast.co.jp/train_info/js/getinformation-jp-shinkansen.js.
Their `setData` functions insert editorial notices from
`https://www.jreast.co.jp/traininfojp/{area}.json` into `.afterwriteinfo`;
they do not provide the current server-rendered route rows. Also inspected
`https://traininfo.jreast.co.jp/train_info/js/train_info_mtd.js` (notice/map UI).

The provider covers route entries only. Limited-express services, separate
Shinkansen train cancellation lists, editorial JSON notices, linked PDFs,
delay certificates and detail-page histories/distribution times are excluded.
The root page publishes a 30-minute delay threshold and a 04:00–02:00 service
window; BRT notices are limited to prolonged suspensions. Normal means no
reported incident under those criteria, not zero delay or trains in service.

Canonical identity decisions: 65 existing IDs are reused, including Yamanote,
the Tokyo Monorail operator's own line, and the existing Hokuriku Shinkansen
ID/operator definition shared with JR West. Provider identity remains JR East;
the pre-existing catalog's Hokuriku operator attribution is unchanged.
Official broad entries for Nambu, Utsunomiya, Saikyo, Kawagoe, Joetsu, Hachiko,
Chuo, Ome, Joban, Narita, Uetsu, Ou and Tohoku have different scopes from the
existing Yahoo section/combined entries. They receive distinct IDs rather
than assigning a broad alert to an arbitrary section. Other new entries are
Sotetsu through services (`GROUP`), Senseki-Tohoku, two BRT routes and four
Shinkansen routes. BRT and railway sections remain separate. Source names
are retained even when the canonical name differs.

Tests use these real incident rows offline via `httpx.MockTransport`.
Recovery, altered labels/classes, route loss, changed identity, missing fields
and transport failures are explicitly synthetic. No real same-incident
recovery or abnormal Shinkansen capture was verified.

Terms reviewed on 2026-11-02:
https://www.jreast.co.jp/site/rules.html/ (scope and copyright/reuse clauses),
and https://traininfo.jreast.co.jp/train_info/ (coverage and accuracy).
Metadata records `PERMISSION_REQUIRED` and both URLs; access is not a reuse
licence.
