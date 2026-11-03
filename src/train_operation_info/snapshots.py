"""Record pre-parser HTTP bodies and replay one provider refresh offline.

The opt-in gzip/deduplication workflow follows ../keihan_tracker (MIT,
dk-butsuri, 2026). Captures also retain request identity and HTTP status so
multi-endpoint and POST-based providers can reproduce a complete refresh.
"""

import asyncio
from collections import defaultdict, deque
from datetime import datetime
import gzip
from hashlib import sha256
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zlib import error as ZlibError

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .models import ProviderId

_LOGGER = logging.getLogger(__name__)
_REPLAY_TIME = "train_operation_info.replay_time"


class RecordedResponse(BaseModel):
    """HTTP-decoded bytes are stored separately, before any parser/charset conversion."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    method: str
    url: str
    request_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str]
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotCapture(BaseModel):
    """One refresh. Recording a mock response does not make it official evidence."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    format_version: Literal[1] = 1
    provider_id: ProviderId
    captured_at: AwareDatetime
    responses: tuple[RecordedResponse, ...]
    error: str | None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class _SnapshotRecorder:
    def __init__(self, directory: str | Path, provider_id: ProviderId) -> None:
        # Provider IDs are built-in constants, but also guard custom subclasses.
        if not provider_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in provider_id):
            raise ValueError("Snapshot provider ID must be a simple directory name")
        self._directory = Path(directory) / provider_id
        self._provider_id = provider_id
        self._last_signature: bytes | None = None
        self._responses: list[RecordedResponse] = []
        self._bodies: dict[str, bytes] = {}

    def begin(self) -> None:
        self._responses = []
        self._bodies = {}

    def record(self, response: httpx.Response) -> None:
        # Key redirects by the original request so replay needs no live redirect.
        request = response.history[0].request if response.history else response.request
        body_hash = sha256(response.content).hexdigest()
        self._bodies[body_hash] = response.content
        self._responses.append(RecordedResponse(
            method=request.method, url=str(request.url),
            request_body_sha256=sha256(request.content).hexdigest(),
            status_code=response.status_code,
            # Do not replay Content-Encoding: httpx has already decoded the body.
            # Authentication, cookies and request headers are not archived.
            headers={key: response.headers[key] for key in ("content-type", "content-language") if key in response.headers},
            body_sha256=body_hash,
        ))

    async def finish(self, captured_at: datetime, error: str | None) -> None:
        # Independent concurrent requests may complete in a different order.
        responses = tuple(sorted(
            self._responses, key=lambda entry: (entry.method, entry.url, entry.request_body_sha256),
        ))
        capture = SnapshotCapture(
            provider_id=self._provider_id, captured_at=captured_at,
            responses=responses, error=error,
        )
        signature = sha256(capture.model_dump_json(exclude={"captured_at"}).encode()).digest()
        if signature == self._last_signature:
            return
        bodies = self._bodies.copy()

        def write() -> None:
            for digest, body in bodies.items():
                path = self._directory / "bodies" / f"{digest}.gz"
                if not path.exists():
                    _atomic_write(path, gzip.compress(body, mtime=0))
            date = captured_at.strftime("%Y%m%d")
            name = f"{captured_at:%H%M%S.%f}_{uuid4().hex[:8]}.json"
            _atomic_write(self._directory / date / name, capture.model_dump_json(indent=2).encode())

        try:
            await asyncio.to_thread(write)
        except OSError as exc:
            # Diagnostics must not prevent the source from updating/recovering.
            _LOGGER.warning("Could not save %s snapshot: %s", self._provider_id, exc)
        else:
            self._last_signature = signature


class SnapshotReplayTransport(httpx.AsyncBaseTransport):
    """Replay exactly one capture; missing requests fail without accessing the network."""

    def __init__(self, capture_path: str | Path) -> None:
        path = Path(capture_path)
        self.capture = SnapshotCapture.model_validate_json(path.read_bytes())
        self._bodies = path.parent.parent / "bodies"
        self._responses: dict[tuple[str, str, str], deque[RecordedResponse]] = defaultdict(deque)
        for entry in self.capture.responses:
            self._responses[(entry.method, entry.url, entry.request_body_sha256)].append(entry)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, str(request.url), sha256(await request.aread()).hexdigest())
        entries = self._responses.get(key)
        if not entries:
            raise httpx.ConnectError(f"No recorded response for {request.method} {request.url}", request=request)
        entry = entries.popleft()

        def read() -> bytes:
            body = gzip.decompress((self._bodies / f"{entry.body_sha256}.gz").read_bytes())
            if sha256(body).hexdigest() != entry.body_sha256:
                raise ValueError("Snapshot body SHA-256 does not match")
            return body

        try:
            body = await asyncio.to_thread(read)
        except (OSError, EOFError, ValueError, ZlibError) as exc:
            raise httpx.ReadError(f"Could not read recorded response: {exc}", request=request) from exc
        return httpx.Response(
            entry.status_code, headers=entry.headers, content=body, request=request,
            extensions={_REPLAY_TIME: self.capture.captured_at},
        )
