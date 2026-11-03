"""Synthetic GTFS-rt feeds for the shared decoder and status rules.

Every feed here is encoded by the test helpers below from the official proto field
numbers; none is a recorded source response. Real MTA data: tests/test_mta_subway.py.
"""

from datetime import datetime, timezone

import pytest

from train_operation_info.exceptions import ParseError
from train_operation_info.models import LINE_CATALOG, AlertEffect, AlertTiming, LineId, LineStatus, ProviderId
from train_operation_info.providers.gtfs_rt import (
    FeedEntity, FeedScope, alert_effect, decode_feed, effect_name, lines_from_feed, route_status,
)

_NOW = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number: int, wire_type: int) -> bytes:
    return _varint(number << 3 | wire_type)


def _uint(number: int, value: int) -> bytes:
    return _key(number, 0) + _varint(value)


def _bytes(number: int, payload: bytes) -> bytes:
    return _key(number, 2) + _varint(len(payload)) + payload


def _str(number: int, text: str) -> bytes:
    return _bytes(number, text.encode())


def _text(number: int, text: str, language: str = "en") -> bytes:
    return _bytes(number, _bytes(1, _str(1, text) + _str(2, language)))


def _selector(route: str | None = None, *, stop: str | None = None, direction: int | None = None,
              trip_route: str | None = None, agency: str = "AG") -> bytes:
    body = _str(1, agency)
    if route is not None:
        body += _str(2, route)
    if trip_route is not None:
        body += _bytes(4, _str(5, trip_route))
    if stop is not None:
        body += _str(5, stop)
    if direction is not None:
        body += _uint(6, direction)
    return _bytes(5, body)


def _alert(*selectors: bytes, effect: int | None = None, header: str = "Synthetic header",
           extra: bytes = b"") -> bytes:
    body = b"".join(selectors) + _text(10, header) + _text(11, "Synthetic description") + extra
    if effect is not None:
        body += _uint(7, effect)
    return body


def _entity(identifier: str, alert: bytes, extra: bytes = b"") -> bytes:
    return _bytes(2, _str(1, identifier) + extra + _bytes(5, alert))


def feed(*entities: bytes, header: bytes | None = None) -> bytes:
    if header is None:
        header = _str(1, "2.0") + _uint(2, 0) + _uint(3, 1793674939)
    return _bytes(1, header) + b"".join(entities)


_LINES = tuple(
    LINE_CATALOG[LineId(f"us:nyct_subway:{route}")].create_line(ProviderId("synthetic"), "https://example.com/")
    for route in ("a", "c")
)
_SCOPE = FeedScope(
    routes={"A": LineId("us:nyct_subway:a"), "C": LineId("us:nyct_subway:c")},
    agency_ids=frozenset(("AG",)), language="en", include=lambda entity: True,
)


def _convert(data: bytes) -> dict[str, tuple[LineStatus, int]]:
    lines = lines_from_feed(decode_feed(data), _LINES, _SCOPE, _NOW)
    return {line.line_id.rsplit(":", 1)[1]: (line.status, len(line.alerts)) for line in lines}


@pytest.mark.parametrize(("selectors", "effect", "expected"), [
    ((_selector("A"),), 1, LineStatus.SUSPENDED),
    ((_selector("A"), _selector("A", stop="A02")), 1, LineStatus.SUSPENDED),
    ((_selector("A", stop="A02"),), 1, LineStatus.ALERT),
    ((_selector("A", direction=0),), 1, LineStatus.ALERT),
    ((_selector(trip_route="A"),), 1, LineStatus.ALERT),
    ((_selector("A"),), 3, LineStatus.DELAYED),
    ((_selector("A", stop="A02"),), 3, LineStatus.ALERT),
    ((_selector("A"),), 2, LineStatus.ALERT),
    ((_selector("A"),), 10, LineStatus.ALERT),
    ((_selector("A"),), None, LineStatus.UNKNOWN),
    ((_selector("A"),), 8, LineStatus.UNKNOWN),
    ((_selector("A"),), 99, LineStatus.UNKNOWN),
])
def test_synthetic_effect_requires_route_wide_selector(
    selectors: tuple[bytes, ...], effect: int | None, expected: LineStatus,
) -> None:
    data = feed(_entity("e1", _alert(*selectors, effect=effect)))
    alert = decode_feed(data).entities[0].alert
    assert alert is not None
    assert route_status(alert, "A") is expected
    assert _convert(data) == {"a": (expected, 1), "c": (LineStatus.NORMAL, 0)}


def test_synthetic_alert_effect_and_labels_follow_the_enum() -> None:
    assert alert_effect(1) is AlertEffect.NO_SERVICE
    assert alert_effect(2) is AlertEffect.REDUCED_SERVICE
    assert alert_effect(3) is AlertEffect.DELAYS
    assert alert_effect(4) is AlertEffect.OTHER
    assert alert_effect(None) is alert_effect(8) is alert_effect(99) is AlertEffect.UNKNOWN
    assert effect_name(None) == "UNKNOWN_EFFECT (absent)"
    assert effect_name(99) == "EFFECT_99"


def test_synthetic_alert_text_periods_and_shared_identity() -> None:
    impact = _bytes(3, _uint(1, 1793700000) + _uint(2, 1793710000))
    shown = _bytes(1, _uint(1, 1793600000))
    data = feed(
        _entity("multi", _alert(_selector("A"), _selector("C", stop="C1"), effect=3,
                                extra=impact + shown + _text(8, "https://example.com/a"))),
        _entity("display-only", _alert(_selector("C"), effect=7, extra=shown)),
        _entity("two-impacts", _alert(_selector("C"), effect=7, extra=impact + impact)),
    )
    lines = lines_from_feed(decode_feed(data), _LINES, _SCOPE, _NOW)
    a, c = lines
    assert a.status is LineStatus.DELAYED and c.status is LineStatus.ALERT
    assert a.updated_at == datetime(2026, 11, 3, 3, 2, 19, tzinfo=timezone.utc)
    assert a.fetched_at == _NOW
    shared = a.alerts[0]
    assert shared == c.alerts[0]
    assert shared.alert_id == "multi"
    assert shared.affected_line_ids == (LineId("us:nyct_subway:a"), LineId("us:nyct_subway:c"))
    assert shared.description == "Synthetic description\nhttps://example.com/a"
    assert shared.effect is AlertEffect.DELAYS and shared.timing is AlertTiming.UNKNOWN
    assert shared.active_from == datetime.fromtimestamp(1793700000, timezone.utc)
    assert shared.active_until == datetime.fromtimestamp(1793710000, timezone.utc)
    display_only, two_impacts = c.alerts[1:]
    # active_period is a display window and several impact ranges are not merged.
    assert display_only.active_from is None and display_only.active_until is None
    assert two_impacts.active_from is None and two_impacts.active_until is None
    assert c.source_status == "SIGNIFICANT_DELAYS, OTHER_EFFECT"


def test_synthetic_alert_without_route_is_unscoped_and_unknown_everywhere() -> None:
    data = feed(_entity("stop-only", _alert(_bytes(5, _str(1, "AG") + _str(5, "S1")), effect=1)))
    lines = lines_from_feed(decode_feed(data), _LINES, _SCOPE, _NOW)
    assert all(line.status is LineStatus.UNKNOWN for line in lines)
    alert, = {a.alert_id: a for line in lines for a in line.alerts}.values()
    assert alert.affected_line_ids == ()


def test_synthetic_scope_filter_skips_entities_before_route_validation() -> None:
    scope = FeedScope(
        routes=_SCOPE.routes, agency_ids=_SCOPE.agency_ids, language="en",
        include=lambda entity: not entity.entity_id.startswith("skip"),
    )
    data = feed(_entity("skip:1", _alert(_selector("NEW"), effect=1)), _entity("keep", _alert(_selector("C"))))
    lines = lines_from_feed(decode_feed(data), _LINES, scope, _NOW)
    assert [line.status for line in lines] == [LineStatus.NORMAL, LineStatus.UNKNOWN]


def test_synthetic_unknown_fields_and_extensions_are_skipped() -> None:
    extension = _bytes(1001, b"\x1a\x06Delays") + _uint(9999, 5) + _key(1500, 5) + b"\x00\x00\x00\x00"
    data = feed(_entity("e1", _alert(_selector("A"), effect=3, extra=extension), extra=_uint(1001, 1)))
    assert _convert(data)["a"] == (LineStatus.DELAYED, 1)


def _header(version: str = "2.0", incrementality: int = 0) -> bytes:
    return _str(1, version) + _uint(2, incrementality)


@pytest.mark.parametrize("data", [
    pytest.param(feed(_entity("e1", _alert(_selector("A"))))[:-3], id="truncated"),
    pytest.param(b"\x0a\x80", id="truncated-length"),
    pytest.param(b"\x08" + b"\xff" * 11, id="long-varint"),
    pytest.param(b"\x0b\x0c", id="group"),
    pytest.param(b"\x07\x00", id="field-zero"),
    pytest.param(feed(header=_uint(1, 2)), id="version-wire-type"),
    pytest.param(feed(header=b""), id="missing-version"),
    pytest.param(_str(2, ""), id="missing-header"),
    pytest.param(feed(header=_header("3.0")), id="version"),
    pytest.param(feed(header=_header(incrementality=1)), id="differential"),
    pytest.param(feed(header=_header() + _str(1, "2.0")), id="duplicate-singular"),
    pytest.param(feed(_entity("e1", _alert(_selector("A")), extra=_uint(2, 1))), id="deleted"),
    pytest.param(feed(_entity("e1", _alert(_selector("A"))), _entity("e1", _alert(_selector("C")))), id="duplicate-id"),
    pytest.param(feed(_bytes(2, _str(1, "e1") + _bytes(3, b""))), id="not-an-alert"),
    pytest.param(feed(_entity("e1", _alert(_selector("A"), header=""))), id="empty-header"),
    pytest.param(feed(_entity("e1", _alert(_selector("A")).replace(b"\x12\x02en", b"\x12\x02ja", 1))), id="no-en-header"),
    pytest.param(feed(_entity("e1", _alert(_selector("A"), extra=_text(10, "Second header")))), id="duplicate-text-field"),
    pytest.param(feed(_entity("e1", _alert(_bytes(5, _str(1, "AG") + _bytes(2, b"A\xff"))))), id="invalid-utf8"),
    pytest.param(feed(_entity("e1", _alert(_selector("NEW")))), id="unregistered-route"),
    pytest.param(feed(_entity("e1", _alert(_selector(trip_route="NEW")))), id="unregistered-trip-route"),
    pytest.param(feed(_entity("e1", _alert(_selector("A", agency="OTHER")))), id="foreign-agency"),
    pytest.param(feed(_entity("e1", _alert(_selector("A"), extra=_bytes(1, _uint(1, 1 << 62))))), id="time-range"),
])
def test_synthetic_malformed_feeds_are_parse_errors(data: bytes) -> None:
    with pytest.raises(ParseError):
        lines_from_feed(decode_feed(data), _LINES, _SCOPE, _NOW)


def test_scope_must_cover_exactly_the_provider_lines() -> None:
    scope = FeedScope(routes={"A": LineId("us:nyct_subway:a")}, agency_ids=frozenset(), language="en",
                      include=lambda entity: True)
    with pytest.raises(ValueError):
        lines_from_feed(decode_feed(feed()), _LINES, scope, _NOW)


def test_include_receives_decoded_entities() -> None:
    seen: list[FeedEntity] = []

    def include(entity: FeedEntity) -> bool:
        seen.append(entity)
        return False

    scope = FeedScope(routes=_SCOPE.routes, agency_ids=_SCOPE.agency_ids, language="en", include=include)
    lines = lines_from_feed(decode_feed(feed(_entity("e1", _alert(_selector("A"))))), _LINES, scope, _NOW)
    assert [entity.entity_id for entity in seen] == ["e1"]
    assert all(line.status is LineStatus.NORMAL and line.source_status == "no alert in scope" for line in lines)
