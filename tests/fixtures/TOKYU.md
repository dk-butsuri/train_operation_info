# Tokyu official source evidence

Retrieved on 2026-11-02 UTC using httpx GET with redirects enabled and
`User-Agent: Mozilla/5.0`. The default httpx User-Agent received HTTP 403 at
that time. The Provider no longer imitates a browser: it sends the shared
`USER_AGENT`, and a refusal is reported as `FetchError` rather than worked around.
JSON files preserve the original response bytes, including the UTF-8 BOM and
CR line endings where present. No states, route labels, times or prose were
edited. The live normal feed contains all nine routes, `check="0"`, route
checks `"0,0"`, and `kousin_jikoku=null`.

| Fixture | Official source | SHA-256 of downloaded original |
| --- | --- | --- |
| [tokyu_normal.json](tokyu_normal.json) | [unten2.json](https://www.tokyu.co.jp/unten/unten2.json) | `127ab21a07ea5d6192a4109eb9fc6c8449d2c3976a42897d4bf8947e02590393` |
| [tokyu_additional_normal.json](tokyu_additional_normal.json) | [unten_additional.json](https://www.tokyu.co.jp/unten/unten_additional.json) | `15c53b41755b7dbbf631697798b043b1eb429674afb2580b605d468c7f8593b7` |
| [tokyu_information_normal.json](tokyu_information_normal.json) | [information.json](https://www.tokyu.co.jp/unten/information.json) | `c17657aeb9321ce12307479829f5e5ae8d941d49cab25258abc235606b78e073` |
| [tokyu_official_script.js](tokyu_official_script.js) | [main.js?tn94mu](https://www.tokyu.co.jp/themes/custom/tokyu_portal2/bundle/main.js?tn94mu) | `13db55fd579b0db86c52fe59f896cc0db24847643e74c00239d1d20f74353d1b` |
| [tokyu_legend.html](tokyu_legend.html) | [operation page](https://www.tokyu.co.jp/unten2/unten.html) | `613dc9a84f4cc9b033692d08392b055e3af2ced0d997dab7479a81952701a0e5` |

The JavaScript fixture is the exact UTF-8 substring starting at
`async function hl()` and ending before `const pl="portal-scroll-top"`.
The HTML fixture is a BeautifulSoup serialization of
`.portal-unten__info-status-description`. Unrelated script/page content was
omitted; the hashes above refer to the full downloaded originals.
`/unten/check.txt` was also inspected: original bytes `0`, SHA-256
`5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9`.
The provider uses the JSON's own `check` field to avoid separately fetched
overall flags disagreeing during an update; both were `0` when reviewed.

The official script's `hl()` lists `ty, mg, sh, dt, om, ik, tm, sg, kd` and
maps them to the nine route names. It splits `check_<route>` into detail display
(first component: 0 hidden, 1 shown, 2 shown with replacement-transport dialog)
and icon (second component: 0 circle, 1/3 triangle, 2 cross). The page legend
establishes that triangles include several different operational changes;
`ALERT` is the faithful common status. Neither delay-only nor partial
suspension can be determined from that icon. Cross establishes suspension.
The script's displayed current time comes from `new Date()` and is not an
update timestamp. Non-null `kousin_jikoku` has not been verified, so the
provider leaves `updated_at=None` and retains nonempty raw values in incident
descriptions. Replacement-transport arrays are not imported.

Wayback CDX was queried for `www.tokyu.co.jp/unten/unten2.json`, successful
JSON captures in 2025–2026, collapsed by month. It listed, among others,
`20250312012113`, `20250911090818`, `20251005221626`, `20251227133143`,
`20260317171320` and `20260807004909`. Replay requests returned HTTP 429;
no archived abnormal response was obtained or used as evidence. All abnormal,
unknown-state, malformed-input, notice and recovery tests are explicitly
synthetic mutations of the normal payload, guided by the official script.
No same-incident recovery, separate partial-suspension code, incident validity
period, or non-null update timestamp was verified.

Terms reviewed on 2026-11-02 UTC: [site terms](https://www.tokyu.co.jp/use/),
section 3 reserves personal private use and statutory uses while requiring
prior permission for other copying, modification, redistribution and public
display. Metadata records `PRIVATE_USE_ONLY`; it does not grant public signage
or commercial reuse. The operation page was checked for source-specific
conditions and states the publication threshold of 15 minutes or suspension.

## 2026-11-07 UTC refusal and later success

A live provider run at 15:08:34 UTC received HTTP 200 for `unten2.json` but
HTTP 403 for `unten_additional.json`, using the shared library User-Agent.
The refresh failed with `FetchError` and did not publish a partial snapshot.
At 15:23:08 UTC the official operation page, additional JSON and information
JSON all returned HTTP 200 with that same User-Agent. Their SHA-256 values
match the originals listed above. At 15:25:41 UTC the page's referenced
`main.js?tn94mu` also returned HTTP 200; its SHA-256 still matches the table,
and its `hl()` still requests the same three `/unten/` JSON URLs. A fresh
provider instance subsequently fetched all nine routes successfully without
first visiting the operation page or changing headers.

These observations establish refusal followed by success, not the cause of
the earlier 403. No alternate URL, browser impersonation, fallback empty
message or special retry is introduced. Additional and general notices are
required because they can change otherwise normal routes to UNKNOWN.
Synthetic regression tests return 403 at each notice endpoint after a
successful suspended snapshot, verify that the entire previous snapshot is
retained without retries, then verify that a later normal response clears
the previous alerts. This is not a captured real-world incident timeline.
