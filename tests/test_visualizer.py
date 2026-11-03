"""The debug display must distinguish source failures from service disruption."""

import asyncio
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import httpx
import pytest

from examples.visualizer import Monitor, demo_state, make_handler
from train_operation_info import Tracker
from train_operation_info.models import LineStatus


def test_demo_is_explicit_and_does_not_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Demo must not fetch")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    state = demo_state()
    assert state.mode == "demo"
    assert any(p.error for p in state.providers)
    assert any(l.status is LineStatus.SUSPENDED for p in state.providers for l in p.lines)
    assert all("演習" in a.title for p in state.providers for l in p.lines for a in l.alerts)
    assert all(l.updated_at is None for p in state.providers for l in p.lines)


def test_failed_refresh_preserves_snapshot_and_exposes_cause() -> None:
    normal = (Path(__file__).parent / "fixtures" / "tokyo_metro_normal.json").read_bytes()

    async def scenario() -> None:
        should_fail = False

        def fail(request: httpx.Request) -> httpx.Response:
            if should_fail:
                raise httpx.ConnectError("offline test", request=request)
            return httpx.Response(200, content=normal)

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            tracker = Tracker(enabled_providers=("tokyo_metro",), client=client)
            monitor = Monitor(tracker)
            await monitor.refresh()
            before = tracker.lines
            assert all(l.status is LineStatus.NORMAL for l in before)
            should_fail = True
            assert monitor.queue_refresh()
            assert not monitor.queue_refresh()
            await monitor.refresh()
            state = monitor.read()
            assert not state.refreshing
            assert state.checked_at is not None
            assert state.providers[0].lines == before
            assert "ConnectError: offline test" in (state.providers[0].error or "")
            assert all(l.status is LineStatus.NORMAL for l in state.providers[0].lines)
            assert all(l.fetched_at is not None for l in state.providers[0].lines)
            assert state.log[1].level == "error"
            assert not monitor.queue_refresh()  # Refresh start is rate limited.

    asyncio.run(scenario())


def test_success_after_failure_clears_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = Tracker(enabled_providers=("tokyo_metro",))
    monitor = Monitor(tracker)

    async def broken() -> None:
        raise RuntimeError("unexpected parser bug")

    monkeypatch.setattr(tracker, "refresh", broken)
    asyncio.run(monitor.refresh())
    assert "unexpected parser bug" in (monitor.read().providers[0].error or "")

    async def succeeds() -> None:
        return None

    monkeypatch.setattr(tracker, "refresh", succeeds)
    asyncio.run(monitor.refresh())
    assert monitor.read().providers[0].error is None
    checked = monitor.read().checked_at
    assert checked is not None and checked <= datetime.now(timezone.utc)


def test_http_demo_assets_and_cross_origin_refresh() -> None:
    monitor = Monitor(Tracker(enabled_providers=("tokyo_metro",)))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(monitor, True))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
            assert client.get("/api/config").json() == {"initial_mode": "demo"}
            demo = client.get("/api/demo")
            assert demo.status_code == 200 and demo.json()["mode"] == "demo"
            assert not monitor.request.is_set()
            for asset in ("/", "/style.css", "/app.js"):
                response = client.get(asset)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
            assert client.get("/../README.md").status_code == 404
            assert client.post("/api/refresh", headers={"Origin": "https://example.com"}).status_code == 403
            assert not monitor.request.is_set()
            assert client.post("/api/refresh").status_code == 202
            assert client.post("/api/refresh").status_code == 429
            assert client.get("/api/state").json()["refreshing"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_worker_closes_its_injected_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    tracker = Tracker(enabled_providers=("tokyo_metro",), client=client)
    completed = Event()

    async def refreshed() -> None:
        completed.set()

    monkeypatch.setattr(tracker, "refresh", refreshed)
    monitor = Monitor(tracker, owned_client=client)
    monitor.thread.start()
    try:
        assert monitor.queue_refresh()
        assert completed.wait(timeout=3)
    finally:
        monitor.close()
    assert client.is_closed
    assert not monitor.thread.is_alive()
