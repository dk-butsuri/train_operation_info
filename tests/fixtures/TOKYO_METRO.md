# Tokyo Metro official current service status

Reviewed 2026-11-02 UTC using public JavaScript inspection and official history.
The [line status page](https://www.tokyometro.jp/unkou/history/ginza.html) loads
[common.js](https://www.tokyometro.jp/library/common/js/common.js), which fetches
[status.json](https://www.tokyometro.jp/library/common/operation/status.json).
The [detail renderer](https://www.tokyometro.jp/library/unkou/js/common.js) displays
`status_info`, `contents`, `section` and `cause`. The Japanese records identify
nine lines using numeric IDs, `name_alpha`, `name_alpha_db` and `line_name`.
The feed spells 東西線 `touzai` / `tozai`, 半蔵門線 `hanzoumon` / `hanzomon`,
and 南北線 `nanboku` / `namboku`; these are explicitly mapped. Marunouchi and
Chiyoda branches are included in their parent line, without separate snapshots.
All nine canonical IDs already exist through Yahoo and are reused unchanged.

[tokyo_metro_manifest.json](tokyo_metro_manifest.json) records source URLs,
UTC retrieval timestamps, original/fixture SHA-256 hashes and extraction.

- `tokyo_metro_normal.json`: live feed projected to `jp`, preserving every
  Japanese field. All lines report `平常運転`, icon `heijou`, status 0 and the
  explicit normal sentence. Several normal records retain old causes such as
  `地震`; these must not create alerts or override the normal label.
- `tokyo_metro_history_ginza.json` and `tokyo_metro_history_touzai.json`:
  first entry for each distinct heading or normal message from the official
  history endpoints. Entry values and order are unchanged. These are history
  evidence, **not abnormal current status.json responses**. They confirm
  `遅延`, `一部列車遅延`, `ダイヤ乱れ`, `運転再開・ダイヤ乱れ`,
  `運転見合わせ`, `折返し運転`, and subsequent normal text. The retained
  suspension is dated 2026-10-20 08:12 JST, restart with disruption 08:34 JST;
  turnbacks are dated 2026-09-30 06:39 JST.
- `tokyo_metro_common.js`: status fetch/render portion of the official common
  script, original lines 1642–1833. Other code is omitted without changing it.
- `tokyo_metro_unkou_script.js` and `tokyo_metro_history_script.js`: unmodified
  detail/history renderers, evidence only. History dates are displayed locally;
  they are never assigned to the independently fetched current snapshots.

The CDX query
`https://web.archive.org/cdx/search/cdx?url=www.tokyometro.jp/library/common/operation/status.json&output=json&filter=statuscode:200&collapse=digest`
returned seven captures: 20180411195313, 20180716171311, 20190323154305,
20190908115423, 20191210194240, 20200307230541, 20231123151610. Replay using
`https://web.archive.org/web/<timestamp>id_/<original>` returned HTTP 429,
including a separate retry of 20190908115423. No archived abnormal JSON or
same-incident current-feed recovery was verified.

Tests using abnormal current-feed records are **synthetic**: the live normal
structure is combined with labels verified in official history, with invented
numeric codes and clearly marked test descriptions. Numeric abnormal codes
and icons are not used to infer severity. Delay labels map to DELAYED,
suspension to SUSPENDED, turnbacks to PARTIAL_SUSPENSION. Timetable disruption
and restart with disruption remain ALERT. Unknown labels, service ended and
contradictory normal records remain UNKNOWN with the text preserved. Normal
requires label, icon, numeric zero and explicit normal text to agree. Empty,
missing, duplicate, unknown or inconsistent route records fail atomically.

No timestamp is supplied by status.json. The displayed `getNow` value is a
current clock, not a source update, so `updated_at=None`. Only a single current
JSON request is made per refresh. Maps, train positions, certificates, history
and independent station/direction statuses are excluded. The server returned
403 to the default httpx User-Agent and 200 with `Mozilla/5.0` at capture time.
The Provider no longer imitates a browser: it sends the shared `USER_AGENT`, and
a refusal is reported as `FetchError` rather than worked around.

The [site terms](https://www.tokyometro.jp/terms/index.html) require permission
for reuse. The operation page independently prohibits unauthorized copying,
reproduction and republication even after changing the presentation. Metadata
therefore records PERMISSION_REQUIRED and both URLs. The current operation
page publishes actual or expected delays of five minutes or more. It warns
that displayed information can differ from actual service. No commercial
reuse grant was found.
