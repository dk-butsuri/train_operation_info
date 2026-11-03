"""Kyoto City Subway's official homepage emergency notices."""

import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("kyoto_subway",))
    await tracker.refresh()
    for line in tracker.kyoto_subway.lines:
        print(line.name, line.status, line.source_status)
    for alert in tracker.kyoto_subway.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
