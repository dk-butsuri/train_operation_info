"""Record live HTTP responses, or replay the latest capture without network access."""

import argparse
import asyncio
from pathlib import Path
from typing import cast, get_args

import httpx

from train_operation_info import ProviderName, Tracker
from train_operation_info.exceptions import RefreshError
from train_operation_info.models import LineStatus
from train_operation_info.snapshots import SnapshotReplayTransport


async def _refresh(tracker: Tracker) -> bool:
    success = True
    try:
        await tracker.refresh()
    except RefreshError as exc:
        success = False
        for source, error in exc.errors.items():
            print(f"{source}: {error}")
    for provider in tracker.providers:
        print(
            provider.provider_id, f"lines={len(provider.lines)}",
            f"affected={len(provider.affected_lines)}", f"unknown={len(provider.unknown_lines)}",
        )
        for line in provider.lines:
            if line.status is not LineStatus.NORMAL:
                print(f"  {line.name}: {line.status.value}")
        for alert in provider.alerts:
            print(f"  {alert.title}\n  {alert.description}")
    return success


async def _record(provider: ProviderName, directory: Path, interval: float | None) -> int:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        tracker = Tracker(enabled_providers=(provider,), client=client, snapshot_dir=directory)
        print(f"Recording to {directory / provider}", flush=True)
        while True:
            success = await _refresh(tracker)
            if interval is None:
                return 0 if success else 1
            await asyncio.sleep(interval)


async def _replay(path: Path) -> int:
    if path.is_dir():
        captures = sorted(path.glob("[0-9]*/*.json"))
        if not captures:
            raise ValueError(f"No captures in {path}")
        path = captures[-1]
    transport = SnapshotReplayTransport(path)
    capture = transport.capture
    if capture.provider_id not in get_args(ProviderName):
        raise ValueError(f"Unknown captured provider: {capture.provider_id}")
    print(f"Replaying {path} (captured at {capture.captured_at.isoformat()})")
    async with httpx.AsyncClient(transport=transport) as client:
        tracker = Tracker(enabled_providers=(cast(ProviderName, capture.provider_id),), client=client)
        return 0 if await _refresh(tracker) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="Record one refresh, or poll until Ctrl+C")
    record.add_argument("--provider", choices=get_args(ProviderName), required=True)
    record.add_argument("--directory", type=Path, default=Path("snapshots"))
    record.add_argument("--interval", type=float, help="Polling interval in seconds (default: one refresh)")
    replay = commands.add_parser("replay", help="Replay a capture file or a provider directory's latest capture")
    replay.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "record" and args.interval is not None and args.interval <= 0:
        parser.error("--interval must be positive")
    try:
        if args.command == "record":
            result = asyncio.run(_record(cast(ProviderName, args.provider), args.directory, args.interval))
        else:
            result = asyncio.run(_replay(args.path))
    except KeyboardInterrupt:
        return
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
