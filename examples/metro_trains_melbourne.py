import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("metro_trains_melbourne",))
    await tracker.refresh()
    for line in tracker.metro_trains_melbourne.lines:
        print(line.name, line.status.value, line.source_status)
    for alert in tracker.metro_trains_melbourne.alerts:
        print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
