# Yurikamome official operation feed

Reviewed 2026-11-02 UTC. The [operation page](https://www.yurikamome.co.jp/ride-guidance/operation.html)
loads [common.js](https://www.yurikamome.co.jp/assets/js/common.js?date=190718),
which fetches the [operation HTML endpoint](https://cms-2.yurikamome.co.jp/api/operation/).
It displays `.info_title`, `.info_update` and `.info_text`, removing the
`[運行状況] ` prefix. The page's initial dash placeholders contain no status.
The [manifest](yurikamome_manifest.json) records source URLs, retrieval times,
original and fixture SHA-256 hashes, and extraction details.

- `yurikamome_normal.html`: unmodified live endpoint response. `平常運転`, explicit
  normal-operation message, distribution time 2026-11-02 04:00 JST.
- `yurikamome_20191003184453.html`: unmodified [Wayback response](https://web.archive.org/web/20191003184453id_/https://cms-2.yurikamome.co.jp/api/operation/),
  captured 2019-10-03 18:44:53 UTC. Its `平常運転` title accompanies only a notice
  of information-service hours, dated 2019-10-04 02:00 JST. It is conservatively
  UNKNOWN because it does not explicitly report current normal operation.
- `yurikamome_operation_script.js`: operation AJAX handler extracted from the
  official script; original labels and logic are preserved. Unrelated script
  content is omitted. This is evidence, not executable test code.

The CDX query `https://web.archive.org/cdx/search/cdx?url=cms-2.yurikamome.co.jp/api/operation/&output=json&filter=statuscode:200&collapse=digest&filter=mimetype:text/html`
returned ten captures: 20191003184453, 20191020133131, 20191228180443,
20200319223943, 20200619161608, 20200916123300, 20201217232037,
20210319053256, 20210621185741, 20211029231406. All were inspected;
none contained an incident. No archived abnormal/recovery response is claimed.

The published switch marks `平常運転` normal, `振替輸送` transfer, and these labels
as abnormal: 運転見合わせ, 運転再開見込, 運転再開, 遅延, 折返し運転,
直通運転再開, 運休, 一部運休, バス代行, 経路変更, リフレッシュ工事,
お知らせ, 直通運転中止, 一部運転再開, お詫び, 自由文.
The parser maps the explicit delay label to DELAYED; suspension and pending
restart to SUSPENDED; partial suspension, turnbacks and partial restart to
PARTIAL_SUSPENSION. Other known notices stay ALERT, including restart notices
which do not themselves establish normal operation. Narrative keywords never
override the title. Unknown titles and nonstandard normal messages stay UNKNOWN
with the source text preserved. Distribution times use Asia/Tokyo.

Tests for every abnormal label, recovery, contradictory/unknown states and
malformed responses are **synthetic**, using the real normal feed structure.
They verify interpretation of the published labels, not historical incidents.
Separate station/direction status and structured cause/section data are not
available from this feed; any such details remain in the notice body. Delay
certificates and timetables are excluded.

The canonical route `jp:operator_c0a210bf19c5:line_cbfd3a81aaf1` (ゆりかもめ線)
is reused from Yahoo route 160/0. Source-specific snapshots remain independent.

The [site policy](https://www.yurikamome.co.jp/utility/policy.html) reserves
copyright and requires permission beyond private copying, quotation and other
uses allowed by law; metadata records PRIVATE_USE_ONLY. No separate commercial
reuse grant was found. The operation page explains its roughly 15-minute
publication threshold, anticipated delays, and possible differences from
actual service. Both pages were reviewed on 2026-11-02 UTC.
