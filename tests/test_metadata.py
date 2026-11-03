"""Human-facing pages and machine request endpoints have independent metadata."""

from typing import get_args

import pytest
from pydantic import ValidationError

from train_operation_info import ProviderName, Tracker
from train_operation_info.models import DataFormat, ProviderMetadata, SourceEndpoint


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
        "jrw": {DataFormat.JSON},
        "jrcentral": {DataFormat.JSON},
        "jrhokkaido": {DataFormat.JSON},
        "jrkyushu": {DataFormat.XML},
        "tokyo_metro": {DataFormat.JSON},
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
