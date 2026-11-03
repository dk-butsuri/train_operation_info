# train_operation_info

**English** | [日本語](https://github.com/dk-butsuri/train_operation_info/blob/main/README.ja.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/dk-butsuri/train_operation_info/blob/main/LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Typed](https://img.shields.io/badge/typing-mypy%20strict-informational.svg)

**Railway service alerts from 38 official sources, in one typed Python API — and it never guesses.**

```python
tracker = Tracker()
await tracker.refresh()
print(tracker.osaka_metro.midosuji.status)  # e.g. LineStatus.DELAYED
```

> **Unofficial.** This library is not affiliated with or endorsed by any railway operator or information provider. Service information belongs to each source. Read [Responsible use](#responsible-use) and the [Disclaimer](#disclaimer) before use.

## Why

- **38 sources, one model.** 29 Japanese operators (all six JR companies, Tokyo Metro, Toei, the major private railways in Tokyo, Nagoya and Osaka, and more), plus Taiwan, Singapore, Germany, France, Austria and New York. Every source returns the same `Line` and `ServiceAlert` models.
- **It never guesses.** A status is mapped only when the source's specification, public code or captured responses prove the mapping. Anything unconfirmed stays `UNKNOWN`, with the original text kept. A failed fetch is never shown as "normal".
- **Typed to the bottom.** Strict, frozen Pydantic models, timezone-aware datetimes, explicit attributes for every line (`tracker.jreast.yamanote`), checked with `mypy --strict`. Ships `py.typed`.
- **A good citizen.** Requests identify the library, never impersonate a browser, and respect a built-in per-source rate limit. Each source's terms of use are recorded in its metadata.
- **Built for signage.** Async refresh, immutable snapshots, last-good data kept on failure, and HTTP record/replay for offline debugging.

## Quick start

Requires Python 3.10+.

```bash
pip install git+https://github.com/dk-butsuri/train_operation_info.git
```

```python
import asyncio
from train_operation_info import Tracker

async def main() -> None:
    tracker = Tracker(enabled_providers=("tokyo_metro", "jreast", "osaka_metro"))
    await tracker.refresh()

    line = tracker.tokyo_metro.ginza
    print(line.name, line.operator.name, line.status)
    print(line.alerts)

    for line in tracker.affected_lines:  # delayed, suspended, or with a notice
        print(line.name, line.status)

asyncio.run(main())
```

`Tracker()` without arguments refreshes every source except the opt-in ones (Yahoo! and MTA). Network access happens only in `await tracker.refresh()`; reading attributes never fetches.

Want to see it first without touching any server? Run the local monitor with synthetic data:

```bash
git clone https://github.com/dk-butsuri/train_operation_info.git
cd train_operation_info
pip install -e .
python -m examples.visualizer --demo   # open http://127.0.0.1:8765
```

## Supported sources

| Region | Sources (`provider_id`) |
| --- | --- |
| Japan — JR | JR Hokkaido (`jrhokkaido`), JR East (`jreast`), JR Central (`jrcentral`), JR West (`jrw`), JR Shikoku (`jrshikoku`), JR Kyushu (`jrkyushu`) |
| Japan — Kanto | Tokyo Metro (`tokyo_metro`), Toei Subway (`toei`), Tobu (`tobu`), Seibu (`seibu`), Keisei (`keisei`), Keio (`keio`), Odakyu (`odakyu`), Tokyu (`tokyu`), Keikyu (`keikyu`), Minatomirai Line (`minatomirai`), Hakone Tozan (`hakone_tozan`), Yurikamome (`yurikamome`), Rinkai Line (`rinkai`) |
| Japan — Chubu / Kansai | Meitetsu (`meitetsu`), Kintetsu (`kintetsu`), Nankai (`nankai`), Hanshin (`hanshin`), Keihan (`keihan`), Hankyu (`hankyu`), Osaka Monorail (`osaka_monorail`), Osaka Metro (`osaka_metro`) |
| Japan — Shikoku / Okinawa | Tosaden Kotsu (`tosaden`), Yui Rail (`yuirail`) |
| Taiwan | Taiwan Railway (`tra`), Taiwan High Speed Rail (`thsr`), Taipei Metro (`taipei_metro`) |
| Singapore | MRT/LRT (`singapore_mrt`) |
| Europe | DB Fernverkehr (`db`), SNCF Transilien (`transilien`), ÖBB (`obb`) |
| United States | MTA New York City Subway (`mta_subway`) — opt-in |
| Aggregator | Yahoo! Japan Transit (`yahoo`) — opt-in, 536 lines nationwide |

Each source covers what its official page publishes, and no more. For per-line attributes, status mappings and exclusions, see the [provider tables](https://github.com/dk-butsuri/train_operation_info/blob/main/README.ja.md#対応provider) and [docs/PROVIDERS.md](https://github.com/dk-butsuri/train_operation_info/blob/main/docs/PROVIDERS.md) (Japanese).

## How it behaves

| `LineStatus` | Meaning |
| --- | --- |
| `NORMAL` | The source states normal operation |
| `DELAYED` | Delays |
| `SUSPENDED` | Service suspended |
| `PARTIAL_SUSPENSION` | Partial cancellation or short-turn operation |
| `ALERT` | A notice whose exact impact the source does not specify |
| `UNKNOWN` | Not fetched yet, or a display the library cannot confirm (raw text kept) |

- **Aggregates**: `tracker.delay_lines`, `tracker.affected_lines`, `tracker.unknown_lines`, `tracker.alerts`, `tracker.active_alerts`.
- **Failures**: a source that cannot be fetched raises `FetchError`; a changed page raises `ParseError`. `tracker.refresh()` updates every selected source, then raises `RefreshError` listing the failures. Failed sources keep their previous snapshot — show their age using `fetched_at`, and never treat a failure as normal service.
- **Rate limit**: 30 seconds per source by default. Refreshing sooner returns the previous snapshot without network access. Set `Tracker(rate_limit=60)` to slow down; anything under 10 seconds is rejected.
- **Time**: every datetime is timezone-aware. `fetched_at` is UTC; source times carry their published offset or local zone.
- **Your own client**: pass a long-lived `httpx.AsyncClient` with `Tracker(client=client)`. If it sets its own User-Agent, that one is used.

```python
from train_operation_info.exceptions import RefreshError

try:
    await tracker.refresh()
except RefreshError as exc:
    for source, error in exc.errors.items():
        print(source, error)
```

## Terms of use metadata

Every source records where its data comes from and what its terms say:

```python
metadata = tracker.tokyo_metro.metadata
print(metadata.terms_url)         # terms of use
print(metadata.usage_permission)  # UsagePermission
print(metadata.usage_note)        # basis and limitations
print(metadata.reviewed_at)       # when the terms were checked
```

| `UsagePermission` | Recorded meaning |
| --- | --- |
| `COMMERCIAL_ALLOWED` | Reuse, including commercial, is explicitly allowed (conditions in `usage_note`) |
| `PRIVATE_USE_ONLY` | Only use permitted by law (e.g. private use) is reserved; anything beyond needs permission |
| `PERMISSION_REQUIRED` | The terms explicitly restrict unauthorized reuse |
| `UNSPECIFIED` | No applicable condition found; ask the source |

Most sources are `PERMISSION_REQUIRED`. These values record published conditions; they are not a legal judgment about your use.

## Record and replay

Save raw HTTP responses while you run, then replay them offline to debug a parser against a real incident:

```python
tracker = Tracker(enabled_providers=("osaka_metro",), snapshot_dir="snapshots")
```

```bash
python -m examples.snapshots replay snapshots/osaka_metro
```

Snapshots stay on your machine; the repository does not include them. See [README.ja.md](https://github.com/dk-butsuri/train_operation_info/blob/main/README.ja.md#http応答の保存とオフライン再生) for the format.

## Responsible use

This library puts the sources' interests ahead of features.

- **It identifies itself.** Every request sends `User-Agent: train_operation_info (+https://github.com/dk-butsuri/train_operation_info)`. It never impersonates a browser.
- **It does not work around refusals.** A source that refuses access raises `FetchError`. The library does not spoof browsers, solve CAPTCHAs, log in, bypass access controls, or rotate addresses to retry.
- **It keeps its distance.** A per-source rate limit of 30 seconds (minimum 10) is always on.
- **It distributes no data.** Captured pages and responses are not included in the repository or the package. Documentation and demos use synthetic data instead of real announcements.
- **It records the terms.** Before showing information in public — a shop or facility display, a website, social media — check the source's current terms and obtain any permission they require.

## For source operators

If you would like this library to stop or change how it accesses your service, please open a [stop or change request](https://github.com/dk-butsuri/train_operation_info/issues/new?template=removal_request.yml). As a rule, we remove the source from the default selection within 7 days and remove or fix it in the next release.

## Contributing

Is your local railway missing? New sources are welcome from any country. Each one has to prove its status mappings with the source's specification, public code or captured responses — see [CONTRIBUTING.md](https://github.com/dk-butsuri/train_operation_info/blob/main/CONTRIBUTING.md) (Japanese) for the rules and steps. Commits must be signed off (`git commit -s`).

```bash
pip install -e ".[dev]"
python -m mypy
python -m pytest
```

## Disclaimer

- Service information belongs to each source. Many sources restrict copying or reuse of their service information.
- Accuracy and timeliness are not guaranteed. For any decision about safety or operations, check the operator's official information.
- Sources may change their pages or APIs at any time, which can break fetching or parsing.

## License

[MIT License](https://github.com/dk-butsuri/train_operation_info/blob/main/LICENSE) © dk-butsuri contributors

The MIT License covers this library's source code only. It does not apply to the service information you fetch with it, which remains subject to each source's terms.
