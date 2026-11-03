"""Typed provider namespaces and concurrent refresh with per-source failures."""

import asyncio
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final, Generic, Literal, NoReturn, Protocol, TypeAlias, TypeVar, cast, get_args, overload

import httpx

from train_operation_info.exceptions import ProviderError, RefreshError
from train_operation_info.models import AlertTiming, Line, ProviderId, ServiceAlert
from train_operation_info.providers.base import AlertProvider, SnapshotProvider, validate_rate_limit
from train_operation_info.providers.db import DbProvider
from train_operation_info.providers.hakone_tozan import HakoneTozanProvider
from train_operation_info.providers.hankyu import HankyuProvider
from train_operation_info.providers.hanshin import HanshinProvider
from train_operation_info.providers.jrcentral import JrCentralProvider
from train_operation_info.providers.jreast import JrEastProvider
from train_operation_info.providers.jrhokkaido import JrHokkaidoProvider
from train_operation_info.providers.jrkyushu import JrKyushuProvider
from train_operation_info.providers.jrshikoku import JrShikokuProvider
from train_operation_info.providers.jrw import JrWestProvider
from train_operation_info.providers.keihan import KeihanProvider
from train_operation_info.providers.keikyu import KeikyuProvider
from train_operation_info.providers.keio import KeioProvider
from train_operation_info.providers.keisei import KeiseiProvider
from train_operation_info.providers.kintetsu import KintetsuProvider
from train_operation_info.providers.meitetsu import MeitetsuProvider
from train_operation_info.providers.minatomirai import MinatomiraiProvider
from train_operation_info.providers.mta_subway import MtaSubwayProvider
from train_operation_info.providers.nankai import NankaiProvider
from train_operation_info.providers.odakyu import OdakyuProvider
from train_operation_info.providers.obb import ObbProvider
from train_operation_info.providers.osaka_metro import OsakaMetroProvider
from train_operation_info.providers.osaka_monorail import OsakaMonorailProvider
from train_operation_info.providers.rinkai import RinkaiProvider
from train_operation_info.providers.seibu import SeibuProvider
from train_operation_info.providers.singapore_mrt import SingaporeMrtProvider
from train_operation_info.providers.taipei_metro import TaipeiMetroProvider
from train_operation_info.providers.thsr import ThsrProvider
from train_operation_info.providers.tobu import TobuProvider
from train_operation_info.providers.toei import ToeiProvider
from train_operation_info.providers.tokyo_metro import TokyoMetroProvider
from train_operation_info.providers.tokyu import TokyuProvider
from train_operation_info.providers.tosaden import TosadenProvider
from train_operation_info.providers.tra import TraProvider
from train_operation_info.providers.transilien import TransilienProvider
from train_operation_info.providers.yahoo import YahooProvider
from train_operation_info.providers.yuirail import YuiRailProvider
from train_operation_info.providers.yurikamome import YurikamomeProvider

# Adding a provider: import it, add its ID here, and add one _Slot line to Tracker.
# A mismatch between this list and the slots fails at import time.
ProviderName: TypeAlias = Literal[
    "db", "obb", "transilien",
    "hakone_tozan", "hankyu", "hanshin", "jrcentral", "jreast", "jrhokkaido", "jrkyushu", "jrshikoku",
    "jrw", "keihan", "keikyu", "keio", "keisei", "kintetsu", "meitetsu", "minatomirai", "nankai", "odakyu",
    "osaka_metro", "osaka_monorail", "rinkai", "seibu", "tobu", "toei", "tokyo_metro", "tokyu",
    "tosaden", "yahoo", "yuirail", "yurikamome",
    "singapore_mrt", "taipei_metro", "thsr", "tra",
    "mta_subway",
]
_ALL_PROVIDERS: tuple[ProviderName, ...] = get_args(ProviderName)
# Yahoo requires explicit selection; constructing Tracker() never fetches it.
# MTA's feed terms forbid apps serving others directly from MTA servers: opt-in.
# Odakyu and DB read an API key published in their own pages; opt-in until permitted.
_OPT_IN_PROVIDERS: tuple[ProviderName, ...] = ("yahoo", "mta_subway", "odakyu", "db")
_DEFAULT_PROVIDERS: tuple[ProviderName, ...] = tuple(
    name for name in _ALL_PROVIDERS if name not in _OPT_IN_PROVIDERS
)

_P = TypeVar("_P", bound=SnapshotProvider)


class _Slot(Generic[_P]):
    """A read-only, precisely typed Tracker attribute holding one provider."""

    def __init__(self, provider_type: type[_P]) -> None:
        self.provider_type = provider_type
        self.name = ""

    def __set_name__(self, owner: type[object], name: str) -> None:
        self.name = name

    def build(self, *, client: httpx.AsyncClient | None, snapshot_dir: str | Path | None) -> _P:
        # Every built-in provider accepts exactly these keywords; the base __init__ does not.
        factory = cast("_Factory[_P]", self.provider_type)
        return factory(client=client, snapshot_dir=snapshot_dir)

    @overload
    def __get__(self, tracker: None, owner: type[object]) -> "_Slot[_P]": ...
    @overload
    def __get__(self, tracker: "Tracker", owner: type[object]) -> _P: ...
    def __get__(self, tracker: "Tracker | None", owner: type[object]) -> "_Slot[_P] | _P":
        if tracker is None:
            return self
        return cast(_P, tracker._by_name[cast(ProviderName, self.name)])

    def __set__(self, tracker: "Tracker", value: NoReturn) -> None:
        raise AttributeError(f"Pass a replacement with Tracker(overrides=...), not tracker.{self.name}")


_P_co = TypeVar("_P_co", bound=SnapshotProvider, covariant=True)


class _Factory(Protocol[_P_co]):
    def __call__(self, *, client: httpx.AsyncClient | None, snapshot_dir: str | Path | None) -> _P_co: ...


class Tracker:
    db = _Slot(DbProvider)
    obb = _Slot(ObbProvider)
    transilien = _Slot(TransilienProvider)
    hakone_tozan = _Slot(HakoneTozanProvider)
    hankyu = _Slot(HankyuProvider)
    hanshin = _Slot(HanshinProvider)
    jrcentral = _Slot(JrCentralProvider)
    jreast = _Slot(JrEastProvider)
    jrhokkaido = _Slot(JrHokkaidoProvider)
    jrkyushu = _Slot(JrKyushuProvider)
    jrshikoku = _Slot(JrShikokuProvider)
    jrw = _Slot(JrWestProvider)
    keihan = _Slot(KeihanProvider)
    keikyu = _Slot(KeikyuProvider)
    keio = _Slot(KeioProvider)
    keisei = _Slot(KeiseiProvider)
    kintetsu = _Slot(KintetsuProvider)
    meitetsu = _Slot(MeitetsuProvider)
    minatomirai = _Slot(MinatomiraiProvider)
    nankai = _Slot(NankaiProvider)
    odakyu = _Slot(OdakyuProvider)
    osaka_metro = _Slot(OsakaMetroProvider)
    osaka_monorail = _Slot(OsakaMonorailProvider)
    rinkai = _Slot(RinkaiProvider)
    seibu = _Slot(SeibuProvider)
    tobu = _Slot(TobuProvider)
    toei = _Slot(ToeiProvider)
    tokyo_metro = _Slot(TokyoMetroProvider)
    tokyu = _Slot(TokyuProvider)
    tosaden = _Slot(TosadenProvider)
    yahoo = _Slot(YahooProvider)
    yuirail = _Slot(YuiRailProvider)
    yurikamome = _Slot(YurikamomeProvider)
    singapore_mrt = _Slot(SingaporeMrtProvider)
    taipei_metro = _Slot(TaipeiMetroProvider)
    thsr = _Slot(ThsrProvider)
    tra = _Slot(TraProvider)
    mta_subway = _Slot(MtaSubwayProvider)

    def __init__(
        self,
        *,
        enabled_providers: tuple[ProviderName, ...] = _DEFAULT_PROVIDERS,
        client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
        # None keeps each provider's default, DEFAULT_RATE_LIMIT seconds.
        rate_limit: float | None = None,
        # Preconfigured providers replace the built ones by provider_id. They keep their
        # own client, snapshot_dir and rate_limit, and are refreshed only if enabled.
        overrides: Iterable[SnapshotProvider] = (),
    ) -> None:
        if len(set(enabled_providers)) != len(enabled_providers) or any(
            name not in _ALL_PROVIDERS for name in enabled_providers
        ):
            raise ValueError("Provider selection contains duplicates or unknown names")
        if rate_limit is not None:
            validate_rate_limit(rate_limit)
        replacements: dict[ProviderName, SnapshotProvider] = {}
        for provider in overrides:
            slot = _SLOTS.get(cast(ProviderName, provider.provider_id))
            if slot is None:
                raise ValueError(f"Unknown provider_id in overrides: {provider.provider_id}")
            if not isinstance(provider, slot.provider_type):
                raise TypeError(f"{slot.name} override must be a {slot.provider_type.__name__}")
            if slot.name in replacements:
                raise ValueError(f"Duplicate override for {slot.name}")
            replacements[cast(ProviderName, slot.name)] = provider
        by_name: dict[ProviderName, SnapshotProvider] = {}
        for name, slot in _SLOTS.items():
            if name in replacements:
                by_name[name] = replacements[name]
                continue
            built = slot.build(client=client, snapshot_dir=snapshot_dir)
            if rate_limit is not None:
                built.rate_limit = rate_limit
            by_name[name] = built
        self._by_name: Mapping[ProviderName, SnapshotProvider] = MappingProxyType(by_name)
        self._providers: tuple[AlertProvider, ...] = tuple(by_name[name] for name in enabled_providers)
        self._refresh_errors: Mapping[ProviderId, ProviderError] = MappingProxyType({})

    @property
    def providers(self) -> tuple[AlertProvider, ...]:
        return self._providers

    @property
    def refresh_errors(self) -> Mapping[ProviderId, ProviderError]:
        return self._refresh_errors

    @staticmethod
    async def _refresh_one(provider: AlertProvider) -> tuple[ProviderId, ProviderError | None]:
        try:
            await provider.refresh()
        except ProviderError as exc:
            return provider.provider_id, exc
        return provider.provider_id, None

    async def refresh(self) -> None:
        results = await asyncio.gather(*(self._refresh_one(provider) for provider in self._providers))
        errors = {identifier: error for identifier, error in results if error is not None}
        self._refresh_errors = MappingProxyType(errors)
        if errors:
            raise RefreshError(errors)

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(line for provider in self._providers for line in provider.lines)

    @property
    def delay_lines(self) -> tuple[Line, ...]:
        return tuple(line for provider in self._providers for line in provider.delay_lines)

    @property
    def affected_lines(self) -> tuple[Line, ...]:
        return tuple(line for provider in self._providers for line in provider.affected_lines)

    @property
    def unknown_lines(self) -> tuple[Line, ...]:
        return tuple(line for provider in self._providers for line in provider.unknown_lines)

    @property
    def alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple(alert for provider in self._providers for alert in provider.alerts)

    @property
    def active_alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple(a for a in self.alerts if a.timing is AlertTiming.ACTIVE)

    @property
    def unclassified_alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple(a for a in self.alerts if a.timing is AlertTiming.UNKNOWN)


def _collect_slots() -> Mapping[ProviderName, "_Slot[SnapshotProvider]"]:
    slots: dict[ProviderName, _Slot[SnapshotProvider]] = {}
    for name, value in vars(Tracker).items():
        if isinstance(value, _Slot):
            slots[cast(ProviderName, name)] = cast("_Slot[SnapshotProvider]", value)
    if set(slots) != set(_ALL_PROVIDERS):
        raise RuntimeError(
            "ProviderName and Tracker slots differ: "
            f"{sorted(set(_ALL_PROVIDERS) ^ set(slots))}",
        )
    for name, slot in slots.items():
        provider_id = getattr(slot.provider_type, "_provider_id", None)
        if provider_id != name:
            raise RuntimeError(f"Tracker.{name} holds a provider with provider_id {provider_id!r}")
    return MappingProxyType(slots)


_SLOTS: Final = _collect_slots()
