"""Provider references stay consistent with refresh and aggregation targets."""

from typing import get_args

import pytest

from train_operation_info import ProviderName, Tracker
from train_operation_info.models import ProviderId
from train_operation_info.providers.keihan import KeihanProvider
from train_operation_info.providers.nankai import NankaiProvider

_NAMES: tuple[ProviderName, ...] = get_args(ProviderName)


def test_every_provider_name_has_a_matching_slot() -> None:
    tracker = Tracker(enabled_providers=_NAMES)
    assert len(tracker.providers) == len(_NAMES)
    for name, provider in zip(_NAMES, tracker.providers):
        assert getattr(tracker, name) is provider
        assert provider.provider_id == ProviderId(name)


def test_default_selection_excludes_only_opt_in_providers() -> None:
    assert {p.provider_id for p in Tracker().providers} == set(_NAMES) - {"yahoo", "mta_subway"}


@pytest.mark.parametrize("provider_name", _NAMES)
def test_provider_reassignment_cannot_diverge_from_registered_provider(
    provider_name: ProviderName,
) -> None:
    tracker = Tracker(enabled_providers=(provider_name,))
    original = tracker.providers[0]
    replacement = Tracker(enabled_providers=(provider_name,)).providers[0]
    assert getattr(tracker, provider_name) is original

    with pytest.raises(AttributeError):
        setattr(tracker, provider_name, replacement)

    assert getattr(tracker, provider_name) is original
    assert tracker.providers == (original,)
    assert tracker.lines == original.lines


def test_override_replaces_slot_even_when_disabled() -> None:
    keihan = KeihanProvider()
    tracker = Tracker(enabled_providers=("nankai",), overrides=(keihan,))
    assert tracker.keihan is keihan
    assert keihan not in tracker.providers


def test_override_with_wrong_class_is_rejected() -> None:
    class Impostor(NankaiProvider):
        _provider_id = ProviderId("keihan")

    with pytest.raises(TypeError, match="KeihanProvider"):
        Tracker(overrides=(Impostor(),))


def test_override_with_unknown_id_is_rejected() -> None:
    class Unknown(NankaiProvider):
        _provider_id = ProviderId("not_a_provider")

    with pytest.raises(ValueError, match="not_a_provider"):
        Tracker(overrides=(Unknown(),))


def test_duplicate_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        Tracker(overrides=(KeihanProvider(), KeihanProvider()))
