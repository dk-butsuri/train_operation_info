# Tobu official source evidence

Investigated on 2026-11-02 UTC using public HTML/JavaScript and archived XML.
Original and fixture SHA-256 hashes, live fetch timestamps, original URLs and
UTC archive timestamps are in [tobu_manifest.json](tobu_manifest.json).

- [Service page](https://www.tobu.co.jp/service_status/):
  `tobu_page.html` extracts `.service-status__info` using BeautifulSoup and
  serializes it as UTF-8. It retains the twelve rows, area notes and publication
  conditions; blank status cells are populated by the separate XML request.
- [Official bundle](https://www.tobu.co.jp/_assets/js/bundle.js):
  `tobu_official_script.js` extracts the ServiceStatus class from its webpack
  module. The module's quoted JavaScript string was decoded with Python's JSON
  decoder; downloaded code was never executed. It shows GET
  `/file/trainop/trainop.xml?dt=...`, paired line/description text, insertion into
  the twelve table rows, and current-time rendering from the HTTP Date header.
  The dt query is a browser-generated cache key, not the source update time.
- [Live XML](https://www.tobu.co.jp/file/trainop/trainop.xml):
  `tobu_normal.xml` is the unmodified response body. All twelve entries state
  `平常どおり運転しています。`. No source update timestamp is present.
- [2024-08-16 07:00:42 UTC XML](https://web.archive.org/web/20240816070042id_/https://www.tobu.co.jp/file/trainop/trainop.xml?dt=1348090380000):
  `tobu_20240816070042.xml` is the unmodified response body. It verifies twelve
  typhoon notices, planned reduced frequency on Skytree/Urban Park, and Tojo
  through-service cancellation. Future risks of delay/suspension occur in prose
  even when trains are operating as scheduled; keyword classification is unsafe.
- [2024-08-27 12:29:46 UTC XML](https://web.archive.org/web/20240827122946id_/https://www.tobu.co.jp/file/trainop/trainop.xml?dt=1440540660000):
  `tobu_20240827122946.xml` is the unmodified response body. Four entries contain
  notices: Nikko express cancellations, Isesaki express cancellation/delay,
  Skytree delays and the northern Isesaki area's delays. The other eight retain
  the exact normal sentence. Cause, sections and named trains remain in text.

The CDX query used `url=www.tobu.co.jp/file/trainop/`, `matchType=prefix`,
successful responses in 2023–2026, collapsed by digest. Replay requests retain
the original query strings and returned these exact timestamps. The original
XML bytes are preserved, including their line endings. Archive capture times
and occurrence times in narrative are not source update timestamps.

## Canonical scope

Skytree through Kuki/Minami-Kurihashi, Urban Park, Tojo and Ogose reuse existing
canonical IDs shared with Yahoo. `source_line_names` preserves XML labels.
Eight units have new `GROUP` IDs because no existing ID represents their scope:
Nikko express, Isesaki express, SL/DL, TH Liner, TJ Liner, Kameido/Daishi together,
Isesaki north (Kuki–Isesaki plus Sano, Kiryu and Koizumi), and Nikko north
(Minami-Kurihashi–Tobu-Nikko plus Utsunomiya and Kinugawa).
Area notices are not projected onto those individual branch IDs. Express/liner
notices do not change conventional route snapshots.

## Status and verification limits

There is no status-code field or dedicated delay/suspension label. The exact
normal sentence maps to `NORMAL`; every other nonempty description is an
`ALERT` with the original text and that publication unit's ID. This includes
unfamiliar notices. `delay_lines` cannot distinguish actual delay, cancellation,
planned service changes or recovery; use `affected_lines` and `alerts`.
No same-incident recovery or distinct suspension-state field was verified.
Clearing notices uses live normal XML. Unknown-route, malformed-envelope,
missing-pair, HTML-description and unfamiliar-notice tests are synthetic.

[Site policy](https://www.tobu.co.jp/sitepolicy/) and service-page usage notes
were reviewed on 2026-11-02 UTC. Articles 7 and 8 reserve statutory private use
and require approval for use beyond that scope and business use. Metadata uses
`PRIVATE_USE_ONLY`. The service page's publication threshold is actual or
expected delays of at least 30 minutes. PDFs, maps, delay certificates and train
position services are not fetched.
