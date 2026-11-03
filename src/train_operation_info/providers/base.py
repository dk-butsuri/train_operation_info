from abc import ABC, abstractmethod
import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import math
from pathlib import Path
from time import monotonic
from typing import ClassVar, Final
from xml.etree.ElementTree import ParseError as XMLParseError

import httpx
from pydantic import ValidationError

from train_operation_info.exceptions import FetchError, ParseError, ProviderError
from train_operation_info.models import LINE_CATALOG, AlertEffect, AlertTiming, Line, LineId, LineStatus, Operator, ProviderId, ProviderMetadata, ServiceAlert
from train_operation_info.snapshots import _REPLAY_TIME, _SnapshotRecorder


class AlertProvider(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Human-facing source, terms, and reviewed usage permission."""

    @property
    @abstractmethod
    def provider_id(self) -> ProviderId:
        """The source ID, independent of the operator."""

    @property
    @abstractmethod
    def lines(self) -> tuple[Line, ...]:
        """The last complete snapshot, initially UNKNOWN."""

    @abstractmethod
    async def refresh(self) -> None:
        """Fetch and atomically replace a complete snapshot or raise."""

    def get_line(self, line_id: LineId) -> Line | None:
        return next((line for line in self.lines if line.line_id == line_id), None)

    @property
    def delay_lines(self) -> tuple[Line, ...]:
        return tuple(line for line in self.lines if line.status is LineStatus.DELAYED)

    @property
    def affected_lines(self) -> tuple[Line, ...]:
        return tuple(
            line for line in self.lines
            if line.status in (
                LineStatus.DELAYED, LineStatus.SUSPENDED,
                LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT,
            )
        )

    @property
    def unknown_lines(self) -> tuple[Line, ...]:
        return tuple(line for line in self.lines if line.status is LineStatus.UNKNOWN)

    @property
    def alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple({
            alert.alert_id: alert for line in self.lines for alert in line.alerts
        }.values())

    @property
    def active_alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple(a for a in self.alerts if a.timing is AlertTiming.ACTIVE)

    @property
    def unclassified_alerts(self) -> tuple[ServiceAlert, ...]:
        return tuple(a for a in self.alerts if a.timing is AlertTiming.UNKNOWN)


def initial_lines(
    namespace: str,
    provider_id: ProviderId,
    source_url: str,
    operator: Operator,
    definitions: tuple[tuple[str, str], ...],
) -> tuple[Line, ...]:
    lines: list[Line] = []
    for key, _ in definitions:
        identifier = LineId(f"{namespace}:{key}")
        definition = LINE_CATALOG.get(identifier)
        if definition is None:
            raise ValueError(f"Register canonical line ID before using it: {identifier}")
        if definition.operator.operator_id != operator.operator_id:
            raise ValueError(f"Canonical operator does not match: {identifier}")
        lines.append(definition.create_line(provider_id, source_url))
    return tuple(lines)


def snapshot(
    line: Line,
    status: LineStatus,
    source_status: str,
    fetched_at: datetime,
    *,
    updated_at: datetime | None = None,
    alerts: tuple[ServiceAlert, ...] = (),
    source_line_names: tuple[str, ...] | None = None,
) -> Line:
    return Line(
        line_id=line.line_id, name=line.name, operator=line.operator,
        provider_id=line.provider_id, source_url=line.source_url, scope=line.scope,
        source_line_names=line.source_line_names if source_line_names is None else source_line_names,
        status=status, source_status=source_status, alerts=alerts,
        fetched_at=fetched_at, updated_at=updated_at,
    )


def make_alert(
    line: Line,
    status: LineStatus,
    title: str,
    description: str,
    *,
    alert_id: str | None = None,
    affected_line_ids: tuple[LineId, ...] | None = None,
    language: str = "ja",
    timing: AlertTiming = AlertTiming.UNKNOWN,
) -> ServiceAlert:
    effect = {
        LineStatus.NORMAL: AlertEffect.OTHER,
        LineStatus.UNKNOWN: AlertEffect.UNKNOWN,
        LineStatus.DELAYED: AlertEffect.DELAYS,
        LineStatus.SUSPENDED: AlertEffect.NO_SERVICE,
        LineStatus.PARTIAL_SUSPENSION: AlertEffect.REDUCED_SERVICE,
        LineStatus.ALERT: AlertEffect.OTHER,
    }[status]
    identifier = alert_id or sha256(
        f"{line.provider_id}:{line.line_id}:{title}:{description}".encode(),
    ).hexdigest()[:24]
    return ServiceAlert(
        alert_id=identifier, title=title, description=description, effect=effect,
        affected_line_ids=(line.line_id,) if affected_line_ids is None else affected_line_ids,
        source_url=line.source_url, language=language,
        timing=timing,
    )


def combined_status(statuses: tuple[LineStatus, ...]) -> LineStatus:
    for status in (
        LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.UNKNOWN,
        LineStatus.DELAYED, LineStatus.ALERT,
    ):
        if status in statuses:
            return status
    return LineStatus.NORMAL


def japanese_status(label: str) -> LineStatus:
    """Only known source labels; never classify an incident from old narrative text."""
    if label in ("平常運転", "通常運転", "通常運行"):
        return LineStatus.NORMAL
    if label in ("遅延", "遅延あり", "一部列車遅延", "遅れ見込み"):
        return LineStatus.DELAYED
    if label in ("運転見合わせ", "順次運転見合わせ", "運休", "運転取り止め", "終日運転取り止め"):
        return LineStatus.SUSPENDED
    if label in ("一部列車運休", "一部列車運休・遅延", "折返し運転"):
        return LineStatus.PARTIAL_SUSPENSION
    if label in ("お知らせ", "行き先変更", "一部列車運休予定", "振替輸送実施中", "振替輸送終了"):
        return LineStatus.ALERT
    return LineStatus.UNKNOWN


DEFAULT_RATE_LIMIT: Final = 30.0
# Out of consideration for source servers, the interval cannot go below this.
MIN_RATE_LIMIT: Final = 10.0
# Requests identify this library instead of imitating a browser. A source that
# refuses it is reported as FetchError and is not worked around.
USER_AGENT: Final = "train_operation_info (+https://github.com/dk-butsuri/train_operation_info)"


def validate_rate_limit(seconds: float) -> float:
    if not math.isfinite(seconds) or seconds < MIN_RATE_LIMIT:
        raise ValueError(f"rate_limit must be a finite number of seconds >= {MIN_RATE_LIMIT:g}")
    return seconds


class SnapshotProvider(AlertProvider):
    """Shared transport and atomic commit for source-specific parsers.

    Like keihan_tracker, a refresh within ``rate_limit`` seconds of the previous
    attempt returns without network access and keeps the current snapshot.
    Failed attempts count, so a failing source is not retried immediately.
    """

    _provider_id: ClassVar[ProviderId]
    _source_url: ClassVar[str]
    _metadata: ClassVar[ProviderMetadata]
    _timeout: ClassVar[float] = 20.0

    def __init__(
        self, lines: tuple[Line, ...], *, client: httpx.AsyncClient | None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        self._lines = lines
        self._client = client
        self._recorder = None if snapshot_dir is None else _SnapshotRecorder(snapshot_dir, self.provider_id)
        self._refresh_lock = asyncio.Lock()
        self._replay_time: datetime | None = None
        self._rate_limit = DEFAULT_RATE_LIMIT
        self._last_attempt: float | None = None
        self._last_error: ProviderError | None = None

    @property
    def rate_limit(self) -> float:
        """Minimum seconds between network refreshes, at least ``MIN_RATE_LIMIT``."""
        return self._rate_limit

    @rate_limit.setter
    def rate_limit(self, seconds: float) -> None:
        self._rate_limit = validate_rate_limit(seconds)

    @property
    def provider_id(self) -> ProviderId:
        return self._provider_id

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    @property
    def lines(self) -> tuple[Line, ...]:
        return self._lines

    def _line(self, suffix: str) -> Line:
        return next(line for line in self._lines if line.line_id.endswith(f":{suffix}"))

    async def refresh(self) -> None:
        async with self._refresh_lock:
            started = monotonic()
            if self._last_attempt is not None and started - self._last_attempt < self._rate_limit:
                # The snapshot is still the result of the failed attempt.
                if self._last_error is not None:
                    raise self._last_error.with_traceback(None)
                return
            self._last_attempt = started
            self._replay_time = None
            if self._recorder is not None:
                self._recorder.begin()
            error: str | None = None
            lines: tuple[Line, ...] = ()
            try:
                lines = await self._refresh_lines()
            except ProviderError as exc:
                self._last_error = exc
                error = f"{type(exc).__name__}: {exc}"
                raise
            except BaseException as exc:
                # Cancellation etc. is not a source failure; allow an immediate retry.
                self._last_attempt = None
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                if self._recorder is not None:
                    captured_at = max(
                        (line.fetched_at for line in lines if line.fetched_at is not None),
                        default=self._now(),
                    )
                    await self._recorder.finish(captured_at, error)
            self._lines = lines
            self._last_error = None

    async def _refresh_lines(self) -> tuple[Line, ...]:
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
                    lines = await self._fetch_lines(client)
            else:
                lines = await self._fetch_lines(self._client)
        except httpx.HTTPError as exc:
            raise FetchError(f"Could not fetch {self.provider_id} official status") from exc
        except (ValidationError, XMLParseError, ValueError) as exc:
            raise ParseError(f"Invalid {self.provider_id} source data: {exc}") from exc
        allowed = self.metadata.statuses | {LineStatus.UNKNOWN}
        if undeclared := {line.status for line in lines} - allowed:
            raise ParseError(f"{self.provider_id} produced undeclared statuses: {undeclared}")
        return lines

    async def _request(
        self, client: httpx.AsyncClient, method: str, url: str, *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if client.headers.get("User-Agent", "").startswith("python-httpx/"):
            # Keep a caller's own User-Agent; replace only httpx's anonymous default.
            headers = {"User-Agent": USER_AGENT, **(headers or {})}
        response = await client.request(method, url, headers=headers, data=data)
        replay_time: object = response.extensions.get(_REPLAY_TIME)
        self._replay_time = replay_time if isinstance(replay_time, datetime) else None
        if self._recorder is not None:
            self._recorder.record(response)
        return response

    async def _get(
        self, client: httpx.AsyncClient, url: str, *, headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return await self._request(client, "GET", url, headers=headers)

    async def _post(
        self, client: httpx.AsyncClient, url: str, *, data: Mapping[str, str],
    ) -> httpx.Response:
        return await self._request(client, "POST", url, data=data)

    @abstractmethod
    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        """Validate the entire source before returning a replacement snapshot."""

    def _now(self) -> datetime:
        return self._replay_time or datetime.now(timezone.utc)
