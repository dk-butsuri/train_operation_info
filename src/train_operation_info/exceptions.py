"""Failures are distinct from normal service and empty alert lists."""

from collections.abc import Mapping
from types import MappingProxyType

from train_operation_info.models import ProviderId


class ProviderError(Exception):
    """A provider could not refresh its data."""


class FetchError(ProviderError):
    """The source could not be fetched."""


class ParseError(ProviderError):
    """The source no longer matches the expected structure."""


class RefreshError(ProviderError):
    """All selected providers finished; one or more kept their old snapshots."""

    def __init__(self, errors: Mapping[ProviderId, ProviderError]) -> None:
        self.errors: Mapping[ProviderId, ProviderError] = MappingProxyType(dict(errors))
        super().__init__("Refresh failed for: " + ", ".join(errors))
