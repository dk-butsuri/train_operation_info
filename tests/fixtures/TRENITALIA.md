# Trenitalia Infomobilità

Investigation on 2026-11-04 UTC: official public HTML/JavaScript and archived
official pages. Original third-party responses remain local and are excluded
from Git. Exact retrieval times, URLs, HTTP statuses and original SHA-256 hashes
are recorded in [trenitalia_manifest.json](trenitalia_manifest.json).

## Source and mapping

- Source: <https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html>.
  The full national notice board is server-rendered in
  `#infomobility-page main .infomobility-list .body-infomobility`.
  The `Infomobility` class in the official `clientlib-site` script filters by
  `data-region` and opens accordions; it does not fetch or paginate the board.
- The canonical `it:trenitalia:network` GROUP describes national traffic
  bulletins, not every train or physical line. Operator: `it:trenitalia`.
  There was no existing Italian group or route to reuse.
- The title `CIRCOLAZIONE REGOLARE`, category `Informazione`, and complete
  five-paragraph national normal bulletin are checked together. Its full
  normalized wording is identical in the 2024-01-02 and 2026-01-01 archives:
  [2024 capture](https://web.archive.org/web/20240102054440id_/https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html),
  [2026 capture](https://web.archive.org/web/20260101154916id_/https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html).
  Only this complete bulletin establishes national `NORMAL`. Exact matching
  includes both languages and the residual-delay caveat. Added commentary,
  quotation elements, negation, scope changes and new wording are not accepted
  as this fixed form. The 2024 legacy layout is evidence of wording stability,
  not a supported runtime layout. The inspected 2025 archive did not contain
  that bulletin and is not used to infer additional status mappings.
- Live 2026-11-04 HTML contains 28 notices, including a high-speed-only normal
  bulletin and a suspension notice. High-speed normality does not establish
  national normality. The national group therefore remains `UNKNOWN`; 26
  in-scope notices are retained with effect `OTHER` and unspecified affected
  lines. No route names, prose tokens or causes classify a delay/cancellation.
- The red `Attenzione` category also labels a recovered incident, while green
  `Informazione` also labels works. Neither colour/category is a traffic-status
  code. New nonempty categories remain notices with unknown operational impact.
- `Programmazione` explicitly classifies planned information and is excluded
  structurally, including its payload validation. Two such notices occur in
  the live capture. Other works remain mixed into `Informazione` and are
  retained. No title-based INFOLAVORI filter is used. Raw HTTP captures still
  include the excluded planned information.
- The 2026 normal capture also contains warning/works notices: `NORMAL` follows
  the explicit national bulletin, while 23 other in-scope notices are retained.
  It does not promise that every train is punctual or every notice has ended.
- Publication days are validated but are not aware update timestamps or incident
  validity periods. `updated_at`, `active_from` and `active_until` are `None`;
  every notice's timing is `UNKNOWN`. Source day/category, title and body text
  are retained. No current date, future date or duration is inferred from prose.
- Linked PDFs, train queries and detail pages are not fetched. ViaggiaTreno
  returned HTTP 403 with the library's identifying User-Agent. No alternate
  host, browser impersonation or refusal workaround was attempted; the runtime
  provider only uses the independently available Trenitalia notice-board URL.

## Verification

`trenitalia_live_20261104.html` and `trenitalia_normal_20260101154916.html` are
byte-for-byte responses. Tests verify original hashes, real normal/abnormal
parsing, retained and excluded notices, and record/replay. Alternating these
captures tests replacement/recovery mechanics; it is not an observed incident
timeline. Empty/malformed content, quotation/negation/future narrative, new
categories, notice deletion, 403/429/503 and parser failures are synthetic.
Missing local captures skip only capture-dependent tests.

## Terms

[Official terms](https://www.trenitalia.com/it/informazioni/termini-e-condizioni-di-utilizzo-sito-trenitalia.html),
reviewed 2026-11-04T11:55:48.813721+00:00. Personal noncommercial saving of
individual extracts is permitted; redistribution/publication requires prior
express consent, with further restrictions on use on other servers/sites.
Metadata records `PERMISSION_REQUIRED`; explicit selection is required.
Public accessibility does not itself grant reuse permission.
