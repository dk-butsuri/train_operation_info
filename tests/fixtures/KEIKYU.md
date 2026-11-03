# 京浜急行電鉄 official provider evidence

The provider fetches only
[the official network-wide service notice](https://unkou.keikyu.co.jp/) and
covers the operator's five canonical lines already registered for other
sources: 京急本線, 京急空港線, 京急大師線, 京急久里浜線, 京急逗子線
(`jp:keikyu:line_78db092fdebd`, `line_f7fdfd13f776`, `line_f45aa080b06c`,
`line_1baf033c4c82`, `line_298c2fc57ddd`). The page never structurally
distinguishes among the five lines, even when its prose names specific
stations or sections, so the single notice is replicated across all five
existing per-line IDs — the same approach `providers/hanshin` uses for its
own site-wide summary — rather than inventing a new combined/`GROUP` ID.
ODPT also publishes Keikyu data, but its licence is challenge-only, so it is
not used here or anywhere in this provider.

## Acquisition

Investigation reused `reports/keikyu_cdx.json` and
`reports/keikyu_cdx_scan.py` (a prior session's CDX listing of every Wayback
capture of `unkou.keikyu.co.jp`, 2015-2026) plus a live fetch of the current
page and its general site terms page. Sampled captures were re-fetched with
`curl --compressed` (the response is UTF-8 and gzip-compressed; a first pass
without `--compressed` produced corrupted bytes, visible as literal `�` in a
naive decode — discovered and corrected before drawing any conclusion from
page content). Byte-length outliers in the CDX listing were used to target
likely incident captures. UTC retrieval times, original URLs and SHA-256 of
the unmodified responses are in [keikyu_manifest.json](keikyu_manifest.json).

## Fixtures

| Fixture | Source / capture | Notice |
| --- | --- | --- |
| `keikyu_normal.html` | Live 2026-11-03 03:35:05.991921 UTC | Exact fixed string "京急線は平常通り運転しています。" |
| `keikyu_20220713030847.html` | [2022-07-13 03:08:47 UTC](https://web.archive.org/web/20220713030847id_/https://unkou.keikyu.co.jp/) | Delay at Kanazawa-Bunko; followed by a 【遅延】 minutes-late detail paragraph in the same `dd` |
| `keikyu_20250730013943.html` | [2025-07-30 01:39:43 UTC](https://web.archive.org/web/20250730013943id_/https://unkou.keikyu.co.jp/) | Tsunami-warning suspension of two sections only (久里浜線/逗子線); 本線 core and 空港線/大師線 are not named |

Each fixture keeps the `h1.heading_title` identity element and the single
`dl.index_unit` block (one `dt` update timestamp, the real `dd` prose, and
the trailing empty `<dd><br /></dd>`) verbatim; surrounding navigation,
scripts and footer markup (irrelevant to parsing) were removed. All three
notices are real captures, not synthetic rewrites.

Further real captures confirmed the same free-text convention with no
separate status field: 2022-02-07 (delay plus an unrelated same-day snow
advisory in a second non-empty `dd`), 2024-09-27 (signal-equipment
inspection delay), and many plain "平常通り運転しています。" captures across
2015-2026, including two early 2022 dates adjacent in time to the incident
captures above. Pre-2019 captures (e.g. 20160614005000, 20180827141025) use
an older `div.unko-panel` template with the same free-text convention but no
`dl.index_unit`/`dt` markup; the current parser does not accept that legacy
layout, and no legacy incident is presented as evidence for the current one.

## Verified mapping and limits

Only the exact string "京急線は平常通り運転しています。" (whitespace-normalized)
maps to `NORMAL`. Everything else keeps all five lines `UNKNOWN` (as hanshin does
for its network-wide notice) with the full `dd` prose
retained in the alert description and `affected_line_ids=()`: the source
provides no structured per-line field, and the 2025-07-30 capture shows that
prose can name a subset of stations/sections while other delay captures use
no stable severity vocabulary at all ("...に遅れ。" alone). We therefore do
not infer DELAYED, SUSPENDED or PARTIAL_SUSPENSION, and do not infer which
of the five lines are affected, from the incident prose; this follows the
project's anti-ad-hoc-inference policy and the `providers/rinkai`/
`providers/hanshin` precedent for sources with no dedicated status code. A
first `dd` that starts with, but is not exactly equal to, the fixed normal
string maps to `UNKNOWN` rather than `NORMAL`; no real capture of this mixed
case was found, so it is unverified and conservative only.

No explicit applicability window is published: `timing` stays `UNKNOWN`,
`active_from`/`active_until` are never set. The `dt` text is an explicit
publication timestamp (not a page-load clock) and is kept as `updated_at`
in `Asia/Tokyo`. The duplicate summary link on the main corporate homepage,
the X/Twitter account, the delay-certificate issuance page and the bad
weather/earthquake PDF are not fetched. Live/current-template abnormal
responses beyond the Wayback captures above are unconfirmed; recovery
(incident followed by a later normal fetch) is verified only via
chronologically later real normal captures of the same URL, not via a
live before/after pair.

## Terms

[General site terms](https://www.keikyu.co.jp/website-guide.html), section 1,
reserve copying to personal/home private use and require prior consent for
other reuse. The service notice page itself additionally states, with no
private-use carve-out: "本内容に関する編集著作権を含む一切の権利は、京浜急行
電鉄株式会社に帰属します。この運行情報を無断で転載・複写すること、また体裁
を変更するなどしてホームページ等で公開することを固く禁じます。" Recorded as
`PERMISSION_REQUIRED`. Both pages were captured; see
[keikyu_manifest.json](keikyu_manifest.json) for retrieval times and hashes.
