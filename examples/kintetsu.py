"""Fetch only Kintetsu's official operation summary."""

import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("kintetsu",))
    await tracker.refresh()
    for line in tracker.kintetsu.lines:
        print(line.name, line.status.value, line.source_status)
    for alert in tracker.kintetsu.alerts:
        print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
