# Osaka Monorail current status map

The official [home page](https://www.osaka-monorail.co.jp/) was fetched with the
library's identifying User-Agent at 2026-11-14 08:59:17 UTC. The response contains
the Japanese network summary and a server-rendered station map. The main line
has six delayed and seven suspended segments; Saito has four delayed segments.
The incident text itself is kept only in the ignored local capture.

[osaka_monorail_manifest.json](osaka_monorail_manifest.json) records exact URLs,
UTC fetch times, original response SHA-256, fixture SHA-256 and extraction methods.
`osaka_monorail_partial_20261114.html` is a BeautifulSoup `html.parser`
serialization of `.operationStatus`, retaining all station IDs, names, segment
classes and summary text without substitution. Copied third-party HTML, CSS and
JavaScript remain local and are excluded from version control.

The public [CSS](https://www.osaka-monorail.co.jp/common/css/common.css?v=1788157719)
was fetched at 08:59:38 UTC. Both `.stationMap__topRail p>span` and
`.stationMap__botRail p>span` define `normal`, `delay` and `stop` with colors
`#2e4fb5`, `#f8de06` and `#fe0200`, respectively. These are the same colors as
`.normalDeatil`, `.delayDeatil` and `.stopDeatil` in the accompanying HTML legend,
which identifies normal, delayed and suspended sections. The Saito junction
`line17-51` has the same class-dependent colors on its connecting pseudo-element.
The CSS, rather than words in the narrative, establishes segment-state meaning.

The map uses stations 11–24 for the main line and 17/51–54 for Saito. Each
`lineA-B` span is a direct child of `p#station_B` in the corresponding rail.
Complete topology is required: all segments suspended means `SUSPENDED`, some
suspended means `PARTIAL_SUSPENSION`, otherwise a delay means `DELAYED`, and
all normal means `NORMAL`. An unknown or ambiguous class makes that route
`UNKNOWN`; missing/duplicate stations or segments and changed topology raise
`ParseError` and retain the previous complete snapshot. Route alerts contain
the original network summary and station-pair names with original class values.
The map is the explicit current operating-status display; mapped delays and
suspensions establish `timing=ACTIVE`. It provides neither an incident validity
period nor a source update timestamp.

[common.js](https://www.osaka-monorail.co.jp/common/js/common.js), fetched at
08:59:39 UTC, opens the detail when `#operationStatus__detail` exists. Its
`dispTime.ts` module fills `#dispTime` from `new Date()` on the reader's device.
That clock, the English duplicate and the standing publication-policy text are
excluded. Scripts and CSS are investigation evidence, not runtime endpoints.
Separate news, planned services and replacement-transport acceptance notices
are outside the consumed status section.

Without a map, the existing exact normal summary establishes `NORMAL`; any
other summary remains an unscoped `UNKNOWN` notice. The older normal fixture
and its archive URL/hash remain documented in [SOURCES.md](SOURCES.md).

The saved live response verifies partial suspension and delay. All-stop maps,
normal map classes, unknown classes, broken topology and transitions from this
incident to the older normal capture are explicitly synthetic tests. No actual
same-incident recovery or live all-stop/normal map response has been captured.
Record/replay tests use the abnormal response through the normal snapshot path.
