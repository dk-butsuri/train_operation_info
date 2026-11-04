import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("mtr",))
    await tracker.refresh()
    for line in tracker.mtr.lines:
        print(line.name, line.status.value, line.source_status)
    for alert in tracker.mtr.alerts:
        print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
