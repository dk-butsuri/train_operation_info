"""Human-facing pages and machine request endpoints have independent metadata."""

import asyncio
import itertools
from pathlib import Path
from typing import get_args

import httpx
import pytest
from pydantic import ValidationError

from train_operation_info import ProviderName, Tracker
from train_operation_info.exceptions import ParseError
from train_operation_info.models import DataFormat, Line, LineStatus, ProviderMetadata, SourceEndpoint
from train_operation_info.providers.osaka_monorail import OsakaMonorailProvider


@pytest.mark.parametrize("provider_name", get_args(ProviderName))
def test_every_provider_declares_its_consumed_data_formats(provider_name: ProviderName) -> None:
    provider = Tracker(enabled_providers=(provider_name,)).providers[0]
    metadata = provider.metadata
    expected = {
        "db": {DataFormat.HTML, DataFormat.JSON},
        "transilien": {DataFormat.JSON},
        "tra": {DataFormat.HTML},
        "hakone_tozan": {DataFormat.HTML},
        "meitetsu": {DataFormat.HTML},
        "sapporo_subway": {DataFormat.HTML},
        "nagoya_subway": {DataFormat.JSON},
        "jrw": {DataFormat.JSON},
        "jrcentral": {DataFormat.JSON},
        "jrhokkaido": {DataFormat.JSON},
        "jrkyushu": {DataFormat.XML},
        "tokyo_metro": {DataFormat.JSON},
        "kyoto_subway": {DataFormat.HTML},
        "yuirail": {DataFormat.JSON},
        "tokyu": {DataFormat.JSON},
        "odakyu": {DataFormat.HTML, DataFormat.JAVASCRIPT, DataFormat.JSON},
        "tobu": {DataFormat.XML},
        "keihan": {DataFormat.JSON, DataFormat.XML},
        "keio": {DataFormat.XML},
        "keisei": {DataFormat.HTML, DataFormat.JAVASCRIPT},
        "seibu": {DataFormat.XML},
        "singapore_mrt": {DataFormat.HTML, DataFormat.JSON},
        "mta_subway": {DataFormat.PROTOBUF},
    }.get(provider_name, {DataFormat.HTML})
    assert {endpoint.format for endpoint in metadata.endpoints} == expected
    assert metadata.endpoints
    assert ProviderMetadata.model_validate_json(metadata.model_dump_json()) == metadata


def test_machine_urls_do_not_substitute_the_human_facing_page() -> None:
    tracker = Tracker(enabled_providers=())
    metadata = tracker.jrw.metadata
    assert str(metadata.source_page_url) == "https://trafficinfo.westjr.co.jp/"
    endpoint, = metadata.endpoints
    assert endpoint.url == "https://trafficinfo.westjr.co.jp/api/v1/trafficinfo.json"
    assert endpoint.method == "GET" and endpoint.format is DataFormat.JSON

    hankyu, = tracker.hankyu.metadata.endpoints
    assert str(tracker.hankyu.metadata.source_page_url).endswith("/railinfo/index.html")
    assert hankyu.url.endswith("/railinfo/include/page_railinfo.html")


@pytest.mark.parametrize("changes", [
    {"url": "not-a-url"},
    {"url": "file:///status.json"},
    {"url": "https://example.com/{area}"},
    {"url": "https://example.com/status.json", "is_template": True},
    {"url": "https://{host}/status.json", "is_template": True},
    {"url": "https://example.com/{area.name}", "is_template": True},
    {"url": "https://example.com/{area!r}", "is_template": True},
    {"url": "https://example.com/{area", "is_template": True},
    {"method": "DELETE"},
    {"format": "csv"},
])
def test_invalid_endpoint_metadata_is_rejected(changes: dict[str, object]) -> None:
    data = SourceEndpoint(
        url="https://example.com/status.json", method="GET", format=DataFormat.JSON,
    ).model_dump()
    with pytest.raises(ValidationError):
        SourceEndpoint.model_validate({**data, **changes})


def test_empty_or_missing_endpoint_list_is_rejected() -> None:
    data = Tracker(enabled_providers=()).jrw.metadata.model_dump()
    with pytest.raises(ValidationError):
        ProviderMetadata.model_validate({**data, "endpoints": ()})
    del data["endpoints"]
    with pytest.raises(ValidationError):
        ProviderMetadata.model_validate(data)


_STATUS_COLUMNS = (
    LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED,
    LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT,
)


@pytest.mark.parametrize("readme", ["README.md", "README.ja.md"])
def test_readme_status_table_matches_declared_statuses(readme: str) -> None:
    text = (Path(__file__).parents[1] / readme).read_text(encoding="utf-8")
    header = "| `provider_id` | " + " | ".join(f"`{s.name}`" for s in _STATUS_COLUMNS) + " |"
    assert text.count(header) == 1
    rows = text.split(header)[1].split("\n")[2:]
    table: dict[str, frozenset[LineStatus]] = {}
    for row in itertools.takewhile(lambda r: r.startswith("| `"), rows):
        name, *cells = (cell.strip() for cell in row.strip("|").split("|"))
        table[name.strip("`")] = frozenset(s for s, cell in zip(_STATUS_COLUMNS, cells, strict=True) if cell == "✓")
    tracker = Tracker(enabled_providers=())
    assert table == {
        name: getattr(tracker, name).metadata.statuses for name in get_args(ProviderName)
    }


@pytest.mark.parametrize("provider_name", get_args(ProviderName))
def test_unknown_is_implicit_and_never_declared(provider_name: ProviderName) -> None:
    statuses = getattr(Tracker(enabled_providers=()), provider_name).metadata.statuses
    assert LineStatus.UNKNOWN not in statuses
    assert LineStatus.NORMAL in statuses


def test_undeclared_status_is_a_parse_error_and_keeps_snapshot() -> None:
    class _Delayed(OsakaMonorailProvider):
        async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
            return tuple(line.model_copy(update={"status": LineStatus.DELAYED}) for line in self.lines)

    provider = _Delayed(client=httpx.AsyncClient())
    assert LineStatus.DELAYED not in provider.metadata.statuses
    before = provider.lines
    with pytest.raises(ParseError, match="undeclared"):
        asyncio.run(provider.refresh())
    assert provider.lines == before
