# ÖBB editorial network incident notices

The ÖBB-Infrastruktur [incident-information page](https://infrastruktur.oebb.at/de/unternehmen/kundinnen-im-mittelpunkt/kundeninformation/vor-der-reise/info-zu-stoerungen-vor-reise)
links to [Unsere ÖBB's traffic overview](https://www.unsereoebb.at/verkehrsmeldungen).
This is a nationwide editorial list, not SCOTTY, a station departure board or
a guarantee that all ÖBB trains/lines are punctual. The canonical `at:obb:network`
is a `GROUP` representing this network-level publication scope. Individual
route endpoints in titles or prose are retained without inventing canonical
line identities or treating the whole network as disrupted.

All retrieval times, original and extracted SHA-256 values, source and archive
URLs, UTC capture times and extraction details are in [obb_manifest.json](obb_manifest.json).
The page's server-rendered overview contains the complete published list;
the saved official [filter script](obb_filter_script.js) filters those existing
DOM items and displays a no-results message. It does not fetch further pages.
The HTML legend binds `data-infotype=streckeninfo` to `Störfall`, separately
from `baustelle` (`Baustelle`). Its JavaScript also generates
`/verkehrsmeldungen~type=streckeninfo~.xml` when only that type is selected.
The live incident-only RSS was empty, corroborating the HTML on 2026-11-03.
Only the HTML URL is requested by the Provider; RSS/JavaScript were research.

| Fixture | Verified source observation |
| --- | --- |
| `obb_20260314200213.html` | The 2026-03-14 archive contains a `streckeninfo` notice, Rosenheim (D)–Kufstein, announcing restrictions from 13 March until 23 March. The notice was published on 12 March before their start. A publication timestamp is not an incident start time. |
| `obb_20260717055055.html` | The archive has both Bad Hofgastein–Bad Gastein, explicitly describing a finished disruption (`Bis 07:36 Uhr war...`), and Linz Hbf–St. Valentin, describing current restrictions. Both have the same dedicated incident category. |
| `obb_no_incidents_20261103.html` | Live overview has 14 construction items and no incident items. Construction includes the long Vienna core S-Bahn closure; these structurally separate items are excluded. |

The March prose describes future restrictions from its publication viewpoint;
no dedicated field identifies applicability at the moment of a fetch. The July
fixture additionally proves that an item can remain listed after its disruption
has ended. Therefore the implementation maps the verified category only to an
`OTHER` alert (`ALERT` existence), `timing=UNKNOWN`, no incident dates and no
inferred delay or suspension. `affected_line_ids=()` and the network `Line.status`
is `UNKNOWN` while any retained notices exist. Unknown categories are retained
as `UNKNOWN` alerts. Empty classified incident list means `NORMAL` **within
this editorial list only**, not absence of all rail disruptions. `source_status`
for the empty result is an English library summary, not a quotation of the site.

The item start-date/modified labels are local datetimes without explicit
timezone. They are retained as text where present in the description and do
not populate `updated_at` or validity dates. Current applicability, full/partial
suspension codes, individual line mappings and train-level punctuality are
unverified and unsupported. Long-term notices classified as `streckeninfo` are
retained without prose filtering. Construction (`baustelle`) payload is outside
scope and is not parsed or validated, although its bytes are captured.

Fixtures are serializations of `main`, with images, SVG, traffic footers,
supplementary links, traffic image containers, social-share and modal elements
removed. Header/type labels, descriptions, item types and displayed date text
are unchanged. Synthetic tests alter structural fields, categories and prose;
they do not represent additional official incidents. The transition from the
July archive to the later live empty list verifies removal of old alerts; it is
not claimed to be a same-incident recovery capture.

The page links to [ÖBB-Holding website terms](https://holding.oebb.at/de/nutzungsbedingungen).
Section 3 limits content to personal noncommercial use, reserves copyright and
requires prior written permission for copying, modification and distribution
and further use. No traffic-specific reuse licence was found. Metadata records
`PERMISSION_REQUIRED`; public RSS availability is not a redistribution licence.
