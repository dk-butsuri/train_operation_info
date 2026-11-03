# Keisei evidence

Retrieved on 2026-11-02 UTC with httpx GET, redirects enabled. The original
source for every HTML capture is <https://www.keisei.co.jp/traininfo/index.php>.
The [manifest](keisei_manifest.json) records the exact source/replay URLs and
SHA-256 hashes of complete downloaded bytes and extracted fixtures. Timestamps
in filenames and Wayback URLs are UTC, not Japanese local time.

HTML fixtures contain BeautifulSoup serializations of `#time`, `#info_dif`, and
`#info_txt` where present, in that order. No route labels, classes, times or
incident text were edited. Navigation, translated boilerplate, maps and scripts
were omitted. `keisei_notice.js` and `keisei_kccmod.js` are unmodified live
responses from `/traininfo/data/notice.js` and `/traininfo/data/kccmod.js`.

| Fixture | Capture (UTC) | Verified state |
| --- | --- | --- |
| keisei_normal.html | Live, 2026-11-02 | 全体の平常運行 (`cls0`) |
| keisei_20260415104003.html | 2026-04-15 10:40:03 | 本線の運転見合わせ (`cls1`)、スカイアクセス・押上の遅れ (`cls2`) |
| keisei_20260516001941.html | 2026-05-16 00:19:41 | 本線の遅れ、押上の一部運休（どちらも `cls2`） |
| keisei_20260813101347.html | 2026-08-13 10:13:47 | 6掲載単位の遅れ。千葉線･千原線と松戸線も確認 |
| keisei_20260903013656.html | 2026-09-03 01:36:56 | 全体の平常運行 |
| keisei_20261016114304.html | 2026-10-16 11:43:04 | 本線・スカイアクセス・押上の遅れと振替輸送本文 |

CDX queries covered successful HTML captures of the original URL in 2023–2026,
collapsed by month and then by day. Full replay URLs are in the manifest. The
HTML contains explicit route/status headings and cause/section fields. `cls2`
is shared by delay and partial cancellation, so the status label is essential.
Affected routes come from the status headings, not mentions of other lines in
the cause or narrative. East Narita was not verified as a separate publication
unit and is not exposed by this Provider. Chiba/Chihara are one publication
group and reuse Yahoo's existing common ID, now explicitly `LineScope.GROUP`.

The `#time` field matches generation time even while service is normal; this
does not establish an incident update time. The provider leaves `updated_at`
unset. No same-incident recovery capture was verified. Tests transition from
archived disruptions to live normal HTML without changing either fixture.

The live `notice.js` has `ja_flg=0`, and retains expired text for October 17.
`kccmod.js` displays text only when the flag is enabled and the reader's time is
strictly between `s_day` and `e_day`. The provider uses timezone-aware fetch time
and Japan local dates to reproduce this interval. Active notices, exact interval
boundaries, unknown status labels and malformed responses are explicitly
synthetic tests. A notice describing specific trains has no asserted affected
route IDs and does not suspend an entire line. Archived HTML fixtures are paired
with the live disabled notice in offline tests; this is not a reconstruction of
the archived notice script.

Terms reviewed 2026-11-02 UTC: the [service page](https://www.keisei.co.jp/traininfo/index.php)
prohibits unapproved reproduction, copying and publication, including publication
after reformatting. Metadata records `PERMISSION_REQUIRED` and the service-page
URL. A separate general site reuse policy was not located in the inspected
navigation. The publication threshold is approximately 15 minutes of actual or
expected delay; normal does not establish that every train is on time.
