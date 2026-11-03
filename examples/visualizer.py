"""Local railway control display. Run with python -m examples.visualizer."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
from threading import Event, Lock, Thread
from time import monotonic
from typing import TYPE_CHECKING, Literal, get_args
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from train_operation_info import ProviderName, Tracker
from train_operation_info.exceptions import RefreshError
from train_operation_info.models import (
    AlertEffect, AlertTiming, Line, LineStatus, ProviderMetadata,
    ServiceAlert,
)

ASSETS = Path(__file__).with_name("visualizer_assets")


class ProviderView(BaseModel):
    metadata: ProviderMetadata
    lines: tuple[Line, ...]
    error: str | None = None


class LogEntry(BaseModel):
    time: datetime
    message: str
    level: Literal["info", "error"] = "info"


class DisplayState(BaseModel):
    mode: Literal["live", "demo"] = "live"
    refreshing: bool = False
    checked_at: datetime | None = None
    elapsed_ms: int | None = None
    providers: tuple[ProviderView, ...] = ()
    log: tuple[LogEntry, ...] = ()


def error_detail(error: BaseException) -> str:
    """Include the transport/parser cause that ProviderError wraps."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__
    return " ← ".join(parts)


class Monitor:
    """One worker and event loop own Tracker; HTTP threads only read snapshots."""

    def __init__(self, tracker: Tracker, *, owned_client: httpx.AsyncClient | None = None) -> None:
        self.tracker = tracker
        self.owned_client = owned_client
        self.lock = Lock()
        self.request = Event()
        self.stopping = Event()
        self.last_started = float("-inf")
        self.state = DisplayState(providers=self.provider_views({}))
        self.thread = Thread(target=self.run, daemon=True, name="rail-monitor")

    def provider_views(self, errors: dict[str, str]) -> tuple[ProviderView, ...]:
        return tuple(ProviderView(
            metadata=p.metadata, lines=p.lines, error=errors.get(p.provider_id),
        ) for p in self.tracker.providers)

    def read(self) -> DisplayState:
        with self.lock:
            return self.state

    def queue_refresh(self) -> bool:
        with self.lock:
            if self.state.refreshing or monotonic() - self.last_started < 10:
                return False
            self.last_started = monotonic()
            self.state = self.state.model_copy(update={"refreshing": True})
            self.request.set()
            return True

    async def refresh(self) -> None:
        started = monotonic()
        errors: dict[str, str] = {}
        try:
            await self.tracker.refresh()
        except RefreshError as exc:
            errors = {str(key): error_detail(value) for key, value in exc.errors.items()}
        except Exception as exc:
            # A broken provider must not silently kill the monitoring thread.
            errors = {str(p.provider_id): error_detail(exc) for p in self.tracker.providers}
        now = datetime.now(timezone.utc)
        elapsed = round((monotonic() - started) * 1000)
        entries = [LogEntry(time=now, message=f"取得完了 / {elapsed} ms / {len(errors)} source errors")]
        entries.extend(LogEntry(time=now, message=f"{key}: {value}", level="error")
                       for key, value in errors.items())
        with self.lock:
            self.state = DisplayState(
                checked_at=now, elapsed_ms=elapsed,
                providers=self.provider_views(errors),
                log=tuple((entries + list(self.state.log))[:60]),
            )

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            while not self.stopping.is_set():
                self.request.wait()
                self.request.clear()
                if not self.stopping.is_set():
                    loop.run_until_complete(self.refresh())
        finally:
            if self.owned_client is not None:
                loop.run_until_complete(self.owned_client.aclose())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def close(self) -> None:
        self.stopping.set()
        self.request.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)


def demo_state() -> DisplayState:
    """Synthetic incidents using the real catalogue; never fetch external data."""
    tracker = Tracker(enabled_providers=("tokyo_metro", "osaka_metro", "jreast", "thsr"))
    now = datetime.now(timezone.utc)
    providers: list[ProviderView] = []
    for provider in tracker.providers:
        lines: list[Line] = []
        for i, line in enumerate(provider.lines):
            state = LineStatus.NORMAL
            alerts: tuple[ServiceAlert, ...] = ()
            if i == 0 and provider.provider_id != "thsr":
                state = LineStatus.DELAYED
                alerts = (ServiceAlert(
                    alert_id=f"demo:{line.line_id}", title="【演習データ】車両点検による遅延",
                    description="これは画面検証用の架空の障害です。車両点検のため、一部列車に約15分の遅れが発生している想定です。実際の運行情報ではありません。",
                    effect=AlertEffect.DELAYS,
                    timing=AlertTiming.ACTIVE, affected_line_ids=(line.line_id,),
                    source_url=line.source_url,
                ),)
            if i == 1 and provider.provider_id == "osaka_metro":
                state = LineStatus.SUSPENDED
                alerts = (ServiceAlert(
                    alert_id=f"demo:{line.line_id}", title="【演習データ】設備点検による運転見合わせ",
                    description="画面検証用の架空の運休です。復旧時刻は未定という想定です。",
                    effect=AlertEffect.NO_SERVICE, affected_line_ids=(line.line_id,),
                    source_url=line.source_url,
                ),)
            lines.append(line.model_copy(update={
                "status": state, "source_status": "演習 / " + state.value,
                "fetched_at": now, "alerts": alerts,
            }))
        # Show a failed source retaining an old snapshot as a distinct state.
        if provider.provider_id == "thsr":
            providers.append(ProviderView(metadata=provider.metadata, lines=provider.lines,
                                          error="FetchError: 【演習】接続タイムアウト / 未取得"))
        else:
            providers.append(ProviderView(metadata=provider.metadata, lines=tuple(lines)))
    return DisplayState(
        mode="demo", checked_at=now, elapsed_ms=128,
        providers=tuple(providers),
        log=(LogEntry(time=now, message="演習モード / 全データは架空 / 外部通信なし"),),
    )


def make_handler(monitor: Monitor, initial_demo: bool) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def json_response(self, status: int, data: str) -> None:
            self.respond(status, data.encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/state":
                self.json_response(200, monitor.read().model_dump_json())
            elif path == "/api/demo":
                self.json_response(200, demo_state().model_dump_json())
            elif path == "/api/config":
                self.json_response(200, json.dumps({"initial_mode": "demo" if initial_demo else "live"}))
            else:
                assets = {"/": ("index.html", "text/html"),
                          "/app.js": ("app.js", "text/javascript"),
                          "/style.css": ("style.css", "text/css")}
                asset = assets.get(path)
                if asset is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self.respond(200, (ASSETS / asset[0]).read_bytes(), asset[1] + "; charset=utf-8")

        def do_POST(self) -> None:
            # A local page is the only supported writer; reject cross-site requests.
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{self.headers.get('Host')}":
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if urlsplit(self.path).path != "/api/refresh":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            accepted = monitor.queue_refresh()
            self.json_response(202 if accepted else 429, json.dumps({"accepted": accepted}))

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="MAGI-inspired local railway service monitor")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="Start with synthetic data, without fetching")
    parser.add_argument("--providers", nargs="+", choices=get_args(ProviderName), help="Sources to monitor (Yahoo, MTA, Odakyu and DB are opt-in)")
    parser.add_argument("--snapshot-dir", type=Path, help="Record HTTP responses for offline debugging")
    parser.add_argument("--system-certificates", action="store_true",
                        help="Verify HTTPS with the OS certificate store (install .[visualizer])")
    args = parser.parse_args()
    client: httpx.AsyncClient | None = None
    if args.system_certificates:
        # The optional backend implements the standard SSLContext interface.
        if TYPE_CHECKING:
            from ssl import SSLContext as SystemSSLContext
        else:
            try:
                from truststore import SSLContext as SystemSSLContext
            except ImportError:
                parser.error('System certificates require: python -m pip install -e ".[visualizer]"')
        context = SystemSSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client = httpx.AsyncClient(verify=context, timeout=20, follow_redirects=True)
    selected = None if args.providers is None else tuple(args.providers)
    tracker = (Tracker(client=client, snapshot_dir=args.snapshot_dir) if selected is None else
               Tracker(enabled_providers=selected, client=client, snapshot_dir=args.snapshot_dir))
    monitor = Monitor(tracker, owned_client=client)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(monitor, args.demo))
    monitor.thread.start()
    print(f"Rail control: http://127.0.0.1:{server.server_port} / Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        monitor.close()


if __name__ == "__main__":
    main()
