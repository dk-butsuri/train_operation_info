"""GTFS-realtime Service Alerts: a typed wire decoder and conservative conversion.

Shared by per-feed providers; each feed declares its own URL, terms, route table
and scope filter. This is not a generic "any URL" provider.

Schema: the official proto2 definition
https://github.com/google/transit/blob/master/gtfs-realtime/proto/gtfs-realtime.proto
(fetched 2026-11-03 UTC, SHA-256 8feff2c5499e0ff08777e203e49ef702e07be0a8376b8bb2126add311a709299).
Only the FeedMessage/FeedHeader/FeedEntity/Alert/TimeRange/EntitySelector/
TripDescriptor/TranslatedString fields used below are decoded; unknown fields and
extensions are skipped as protobuf requires. The decoder is deliberately small
instead of gtfs-realtime-bindings: those bindings type-check strictly only with
the separate types-protobuf stubs (without them every message is Any), and they
cannot read agency extensions without compiling further .proto files.

Validation: truncated data, wire-type mismatches of known fields, duplicated
singular fields, groups, invalid UTF-8, missing required fields, unsupported
versions, DIFFERENTIAL feeds, is_deleted entities and duplicate entity IDs raise
ParseError, so the provider keeps its previous snapshot.

Mapping to the common model (no prose is read):
- Line status per alert and route: NO_SERVICE -> SUSPENDED and
  SIGNIFICANT_DELAYS -> DELAYED only when a selector names that route alone
  (agency_id/route_type allowed; no stop_id, trip or direction_id). Every other
  explicit effect, and those two effects with a narrower selector, is ALERT.
  An absent effect (proto default UNKNOWN_EFFECT), UNKNOWN_EFFECT or an
  unrecognised enum number is UNKNOWN; the alert text is kept verbatim.
- ServiceAlert.effect follows the enum directly: NO_SERVICE, REDUCED_SERVICE,
  SIGNIFICANT_DELAYS -> DELAYS, unknown -> UNKNOWN, all others -> OTHER.
- timing is always UNKNOWN: no GTFS-rt field states that an incident is in
  effect now. active_period is the time the alert "should be shown to the user"
  (a display window), so it never populates active_from/active_until. Only a
  single impact_period ("time when the services are affected") does; several
  ranges are not merged into one.
- route_id (or a selector trip's route_id) must be in the feed's verified table,
  and an explicit agency_id must be one of the feed's agencies; otherwise the
  feed is rejected. An alert naming no route at all is kept once with
  affected_line_ids=() and makes every line UNKNOWN, as its scope is unknown.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from train_operation_info.exceptions import ParseError
from train_operation_info.models import AlertEffect, AlertTiming, Line, LineId, LineStatus, ServiceAlert
from .base import combined_status, snapshot

_VARINT: Final = 0
_I64: Final = 1
_LEN: Final = 2
_I32: Final = 5

# Alert.Effect numbers from the official proto.
NO_SERVICE: Final = 1
SIGNIFICANT_DELAYS: Final = 3
_EFFECT_NAMES: Final = {
    1: "NO_SERVICE", 2: "REDUCED_SERVICE", 3: "SIGNIFICANT_DELAYS", 4: "DETOUR",
    5: "ADDITIONAL_SERVICE", 6: "MODIFIED_SERVICE", 7: "OTHER_EFFECT",
    8: "UNKNOWN_EFFECT", 9: "STOP_MOVED", 10: "NO_EFFECT", 11: "ACCESSIBILITY_ISSUE",
}
_UNKNOWN_EFFECT: Final = 8
_ALERT_EFFECTS: Final = {
    1: AlertEffect.NO_SERVICE, 2: AlertEffect.REDUCED_SERVICE, 3: AlertEffect.DELAYS,
    8: AlertEffect.UNKNOWN,
}
_VERSIONS: Final = frozenset(("1.0", "2.0"))


@dataclass(frozen=True)
class _Field:
    number: int
    wire_type: int
    # A varint value, or the raw bytes of a length-delimited/fixed-width field.
    value: int | bytes


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if offset >= len(data):
            raise ParseError("GTFS-rt varint is truncated")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if result >= 1 << 64:
                raise ParseError("GTFS-rt varint exceeds 64 bits")
            return result, offset
        shift += 7
        if shift >= 70:
            raise ParseError("GTFS-rt varint is too long")


def _parse_fields(data: bytes) -> tuple[_Field, ...]:
    fields: list[_Field] = []
    offset = 0
    while offset < len(data):
        key, offset = _varint(data, offset)
        number, wire_type = key >> 3, key & 7
        if number == 0:
            raise ParseError("GTFS-rt field number 0 is invalid")
        value: int | bytes
        if wire_type == _VARINT:
            value, offset = _varint(data, offset)
        elif wire_type in (_LEN, _I64, _I32):
            if wire_type == _LEN:
                size, offset = _varint(data, offset)
            else:
                size = 8 if wire_type == _I64 else 4
            if offset + size > len(data):
                raise ParseError("GTFS-rt field is truncated")
            value, offset = data[offset:offset + size], offset + size
        else:
            # Groups (3/4) are not used by GTFS-rt; 6/7 are invalid.
            raise ParseError(f"Unsupported GTFS-rt wire type {wire_type}")
        fields.append(_Field(number, wire_type, value))
    return tuple(fields)


class _Message:
    """Typed access to one decoded message; unknown field numbers are ignored."""

    def __init__(self, data: bytes, name: str) -> None:
        self._name = name
        self._fields = _parse_fields(data)

    def _all(self, number: int, wire_type: int) -> tuple[_Field, ...]:
        found = tuple(field for field in self._fields if field.number == number)
        if any(field.wire_type != wire_type for field in found):
            raise ParseError(f"GTFS-rt {self._name} field {number} has the wrong wire type")
        return found

    def _one(self, number: int, wire_type: int) -> _Field | None:
        found = self._all(number, wire_type)
        if len(found) > 1:
            raise ParseError(f"GTFS-rt {self._name} field {number} is duplicated")
        return found[0] if found else None

    def uint(self, number: int) -> int | None:
        field = self._one(number, _VARINT)
        if field is None:
            return None
        assert isinstance(field.value, int)
        return field.value

    def int32(self, number: int) -> int | None:
        value = self.uint(number)
        if value is None:
            return None
        signed = value - (1 << 64) if value >= 1 << 63 else value
        if not -(1 << 31) <= signed < 1 << 31:
            raise ParseError(f"GTFS-rt {self._name} field {number} is not an int32")
        return signed

    def boolean(self, number: int) -> bool:
        value = self.uint(number)
        if value not in (None, 0, 1):
            raise ParseError(f"GTFS-rt {self._name} field {number} is not a bool")
        return value == 1

    def _bytes(self, field: _Field) -> bytes:
        assert isinstance(field.value, bytes)
        return field.value

    def string(self, number: int) -> str | None:
        field = self._one(number, _LEN)
        if field is None:
            return None
        try:
            return self._bytes(field).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"GTFS-rt {self._name} field {number} is not UTF-8") from exc

    def required_string(self, number: int) -> str:
        value = self.string(number)
        if value is None:
            raise ParseError(f"GTFS-rt {self._name} required field {number} is missing")
        return value

    def message(self, number: int, name: str) -> "_Message | None":
        field = self._one(number, _LEN)
        return None if field is None else _Message(self._bytes(field), name)

    def messages(self, number: int, name: str) -> tuple["_Message", ...]:
        return tuple(_Message(self._bytes(field), name) for field in self._all(number, _LEN))


def _time(seconds: int | None) -> datetime | None:
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ParseError(f"GTFS-rt POSIX time is out of range: {seconds}") from exc


@dataclass(frozen=True)
class Translation:
    text: str
    language: str | None


@dataclass(frozen=True)
class TranslatedString:
    translations: tuple[Translation, ...]

    def text(self, language: str) -> str | None:
        """The translation in exactly ``language``; other languages are not substituted."""
        found = [item.text for item in self.translations if item.language == language]
        if len(found) > 1:
            raise ParseError(f"GTFS-rt text has duplicate {language!r} translations")
        return found[0] if found else None


@dataclass(frozen=True)
class TimeRange:
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class EntitySelector:
    agency_id: str | None
    route_id: str | None
    route_type: int | None
    stop_id: str | None
    direction_id: int | None
    has_trip: bool
    # TripDescriptor.route_id of a trip selector.
    trip_route_id: str | None

    @property
    def is_route_wide(self) -> bool:
        """The selector names a route alone, not a stop, trip or direction."""
        return (
            self.route_id is not None and self.stop_id is None
            and self.direction_id is None and not self.has_trip
        )


@dataclass(frozen=True)
class Alert:
    active_periods: tuple[TimeRange, ...]
    impact_periods: tuple[TimeRange, ...]
    informed_entities: tuple[EntitySelector, ...]
    # Raw enum numbers; None means the field is absent.
    cause: int | None
    effect: int | None
    url: TranslatedString | None
    header_text: TranslatedString | None
    description_text: TranslatedString | None


@dataclass(frozen=True)
class FeedEntity:
    entity_id: str
    alert: Alert | None


@dataclass(frozen=True)
class FeedMessage:
    gtfs_realtime_version: str
    timestamp: datetime | None
    entities: tuple[FeedEntity, ...]


def _translated(message: _Message | None) -> TranslatedString | None:
    if message is None:
        return None
    return TranslatedString(tuple(
        Translation(item.required_string(1), item.string(2))
        for item in message.messages(1, "Translation")
    ))


def _ranges(message: _Message, number: int) -> tuple[TimeRange, ...]:
    return tuple(
        TimeRange(_time(item.uint(1)), _time(item.uint(2)))
        for item in message.messages(number, "TimeRange")
    )


def _selector(message: _Message) -> EntitySelector:
    trip = message.message(4, "TripDescriptor")
    return EntitySelector(
        agency_id=message.string(1), route_id=message.string(2),
        route_type=message.int32(3), stop_id=message.string(5),
        direction_id=message.uint(6), has_trip=trip is not None,
        trip_route_id=None if trip is None else trip.string(5),
    )


def _alert(message: _Message) -> Alert:
    return Alert(
        active_periods=_ranges(message, 1),
        impact_periods=_ranges(message, 3),
        informed_entities=tuple(_selector(item) for item in message.messages(5, "EntitySelector")),
        cause=message.uint(6), effect=message.uint(7),
        url=_translated(message.message(8, "TranslatedString")),
        header_text=_translated(message.message(10, "TranslatedString")),
        description_text=_translated(message.message(11, "TranslatedString")),
    )


def decode_feed(data: bytes) -> FeedMessage:
    """Decode and validate a complete FULL_DATASET FeedMessage."""
    root = _Message(data, "FeedMessage")
    header = root.message(1, "FeedHeader")
    if header is None:
        raise ParseError("GTFS-rt FeedHeader is missing")
    version = header.required_string(1)
    if version not in _VERSIONS:
        raise ParseError(f"Unsupported GTFS-rt version: {version}")
    if header.uint(2) not in (None, 0):
        raise ParseError("GTFS-rt DIFFERENTIAL feeds are not supported")
    entities: list[FeedEntity] = []
    for item in root.messages(2, "FeedEntity"):
        identifier = item.required_string(1)
        if item.boolean(2):
            raise ParseError(f"GTFS-rt entity is deleted in a full dataset: {identifier}")
        alert = item.message(5, "Alert")
        entities.append(FeedEntity(identifier, None if alert is None else _alert(alert)))
    if len({entity.entity_id for entity in entities}) != len(entities):
        raise ParseError("GTFS-rt entity IDs are duplicated")
    return FeedMessage(version, _time(header.uint(3)), tuple(entities))


def effect_name(effect: int | None) -> str:
    if effect is None:
        return "UNKNOWN_EFFECT (absent)"
    return _EFFECT_NAMES.get(effect, f"EFFECT_{effect}")


def _known_effect(effect: int | None) -> bool:
    return effect is not None and effect in _EFFECT_NAMES and effect != _UNKNOWN_EFFECT


def route_status(alert: Alert, route_id: str) -> LineStatus:
    """The status one alert gives one route, using only effect and selector shape."""
    if not _known_effect(alert.effect):
        return LineStatus.UNKNOWN
    wide = any(
        selector.is_route_wide and selector.route_id == route_id
        for selector in alert.informed_entities
    )
    if wide and alert.effect == NO_SERVICE:
        return LineStatus.SUSPENDED
    if wide and alert.effect == SIGNIFICANT_DELAYS:
        return LineStatus.DELAYED
    return LineStatus.ALERT


def alert_effect(effect: int | None) -> AlertEffect:
    if not _known_effect(effect):
        return AlertEffect.UNKNOWN
    assert effect is not None
    return _ALERT_EFFECTS.get(effect, AlertEffect.OTHER)


@dataclass(frozen=True)
class FeedScope:
    """One feed's verified route table and documented scope filter."""

    # GTFS route_id -> canonical line, verified against the operator's static GTFS.
    routes: Mapping[str, LineId]
    agency_ids: frozenset[str]
    language: str
    # False excludes an entity (e.g. structurally separated planned work). It may
    # raise ParseError for an entity whose category cannot be established.
    include: Callable[[FeedEntity], bool]


def _routes(alert: Alert, scope: FeedScope) -> tuple[str, ...]:
    routes: list[str] = []
    for selector in alert.informed_entities:
        if selector.agency_id is not None and selector.agency_id not in scope.agency_ids:
            raise ParseError(f"Unknown GTFS-rt agency_id: {selector.agency_id}")
        for route in (selector.route_id, selector.trip_route_id):
            if route is None:
                continue
            if route not in scope.routes:
                raise ParseError(f"Unregistered GTFS-rt route_id: {route}")
            if route not in routes:
                routes.append(route)
    return tuple(routes)


def lines_from_feed(
    feed: FeedMessage, lines: tuple[Line, ...], scope: FeedScope, fetched_at: datetime,
) -> tuple[Line, ...]:
    """Validate every in-scope alert, then build a complete replacement snapshot."""
    by_line: dict[LineId, list[tuple[ServiceAlert, LineStatus, str]]] = {line.line_id: [] for line in lines}
    if set(scope.routes.values()) != set(by_line):
        raise ValueError("GTFS-rt route table does not match the provider lines")
    unscoped: list[tuple[ServiceAlert, str]] = []
    source_url = lines[0].source_url
    for entity in feed.entities:
        alert = entity.alert
        if alert is None:
            raise ParseError(f"GTFS-rt entity in an alerts feed has no alert: {entity.entity_id}")
        if not scope.include(entity):
            continue
        title = None if alert.header_text is None else alert.header_text.text(scope.language)
        if not title:
            raise ParseError(f"GTFS-rt alert has no {scope.language!r} header: {entity.entity_id}")
        details = None if alert.description_text is None else alert.description_text.text(scope.language)
        link = None if alert.url is None else alert.url.text(scope.language)
        routes = _routes(alert, scope)
        impact = alert.impact_periods[0] if len(alert.impact_periods) == 1 else None
        line_ids = tuple(dict.fromkeys(scope.routes[route] for route in routes))
        service_alert = ServiceAlert(
            alert_id=entity.entity_id, title=title,
            description="\n".join(text for text in (details, link) if text),
            effect=alert_effect(alert.effect), timing=AlertTiming.UNKNOWN,
            affected_line_ids=line_ids, source_url=source_url, language=scope.language,
            active_from=None if impact is None else impact.start,
            active_until=None if impact is None else impact.end,
        )
        label = effect_name(alert.effect)
        if not routes:
            unscoped.append((service_alert, label))
            continue
        statuses: dict[LineId, LineStatus] = {}
        for route in routes:
            # Several route_ids may share one line; keep the most severe status.
            identifier = scope.routes[route]
            status = route_status(alert, route)
            previous = statuses.get(identifier)
            statuses[identifier] = status if previous is None else combined_status((previous, status))
        for identifier, status in statuses.items():
            by_line[identifier].append((service_alert, status, label))
    result: list[Line] = []
    for line in lines:
        entries = by_line[line.line_id] + [(alert, LineStatus.UNKNOWN, label) for alert, label in unscoped]
        if not entries:
            result.append(snapshot(
                line, LineStatus.NORMAL, "no alert in scope", fetched_at, updated_at=feed.timestamp,
            ))
            continue
        result.append(snapshot(
            line, combined_status(tuple(status for _, status, _ in entries)),
            ", ".join(dict.fromkeys(label for _, _, label in entries)), fetched_at,
            updated_at=feed.timestamp, alerts=tuple(alert for alert, _, _ in entries),
        ))
    return tuple(result)
