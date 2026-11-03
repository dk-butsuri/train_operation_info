import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("nagoya_subway",))
    await tracker.refresh()
    for line in tracker.nagoya_subway.lines:
        print(line.name, line.status.value, line.source_status)
    for alert in tracker.nagoya_subway.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
