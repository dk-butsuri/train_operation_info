import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("tobu",))
    await tracker.refresh()
    for line in tracker.tobu.lines:
        print(line.name, line.status.value, line.source_status)
    for alert in tracker.tobu.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
