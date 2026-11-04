# SNCF TGV open-data service notices

Investigation: public official XML/metadata and live abnormal responses on
2026-11-04 UTC. Exact retrieval times, original HTTP statuses and SHA-256 hashes
are recorded in [tgv_manifest.json](tgv_manifest.json). Captured third-party
responses remain local and are excluded from Git and distributions.

## Source identity and joins

- [Official dataset](https://transport.data.gouv.fr/datasets/horaires-sncf)
  publishes NeTEx and SIRI SX, and documents the commercial train number as
  the link between them. It notes that Service Alerts only cover notices
  assigned to individual journeys, rather than every station/network event.
- NeTEx `ServiceJourney.BrandingRef` is `OUI`, `TGVOUIGO` or `LYR` and
  `TransportSubmode.RailSubmode` is `highSpeedRail` for covered services.
  The live timetable contains 9,942 OUI, 550 TGVOUIGO and 303 LYR journeys.
  Other observed brands are TER, IC, ICN, OUIGO_TC, DBS and SNF.
  TrainNumberRef resolves the declared `TrainNumber.ForAdvertisement`, without
  parsing opaque IDs. `responsibilitySetRef` carries the numeric operator
  identity also present in SIRI `AffectedVehicleJourney.Operator.OperatorRef`.
  The live capture's train 8571 resolves to SNCF's covered services, and its
  corresponding SIRI notice explicitly describes its TGV INOUI service.
- TER, IC, ICN, OUIGO_TC and DBS are excluded brands. SNF/new brands, missing
  or conflicting joins, and notices lacking journey selectors are unresolved
  rather than discarded. A new high-speed brand is never guessed to be TGV.
- Canonical group `fr:sncf:tgv`, operator `fr:sncf_voyageurs`, has no overlap
  with the pre-existing Transilien groups. It covers published train-specific
  INOUI/high-speed OUIGO/Lyria notices, not every international TGV-branded
  service, each physical route or individual train punctuality.

## Status, timing and publication scope

- Both complete inputs must validate before a replacement snapshot commits.
  No timetable brand/number/opcode is inferred from incident prose.
- An individual train's notice cannot establish the operational state of
  the whole group: any included or unresolved notice gives `UNKNOWN`.
  French title, description, original detail HTML (including links), operator
  and train numbers, Progress and Severity remain in alerts, with effect
  `OTHER` and `affected_line_ids=()`.
- No included or unresolved notice means `NORMAL` **only within the declared
  Service Alerts publication scope**, not every train being on time. Empty
  and recovery responses were not independently observed: those tests are
  synthetic, based on the source's incident-list structure.
- The live feed labels cancellation notices `Severity=slight`. Severity and
  Progress are not mapped to delay, suspension or ACTIVE timing. All timing
  remains UNKNOWN. ValidityPeriod is not treated as a verified operational
  impact interval; active bounds remain None. ResponseTimestamp is exposed
  as the feed's generation timestamp, not an individual incident update.
- Planned work and long-duration information share the same publication
  structure. There is no supported structural exclusion for these notices;
  all in-scope/unresolved notices are retained. NeTEx ServiceAlteration=planned
  describes scheduled timetable journeys, not planned incidents.
- Full raw captures also include out-of-scope TER/IC/etc. Each refresh downloads
  both full inputs, keeping record/replay self-contained. The timetable ZIP
  was 32,228,785 bytes; its XML member was 653,982,579 bytes. It is parsed
  incrementally in a worker thread and this provider requires explicit selection.

## Captures and verification

`tgv_netex_20261104.zip` and `tgv_alerts_20261104.xml` are byte-for-byte original
responses. The latter contains 541 situations. Against this timetable the
parser retains 128 covered or unresolved notices; it does not claim all 128
are TGV-specific. The tests verify original hashes, a concrete train-number
join, conservative effects/timing and record/replay. No archived abnormal,
normal or recovery timeline was used. Unknown brands, conflicting numbers,
empty/recovered lists, malformed data and HTTP 403/429/503 are synthetic cases.

The passenger website returned 403 to the identifying library User-Agent.
It is not accessed at runtime, impersonated or bypassed. Independently published
Open Data endpoints returned 200 with the same identifying User-Agent.

## Terms

The [official dataset metadata](https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/temps-reel-siri-sx-lite)
states Open Database License (ODbL), linking to the
[SNCF terms](https://data.sncf.com/pages/cgu/A1#A1).
[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) permits reuse including
commercial use, subject to attribution, licence notices and applicable
share-alike conditions. Individual content rights are not automatically
licensed by database rights. Metadata records COMMERCIAL_ALLOWED with these
conditions; this is not a blanket clearance for every use of every content item.
