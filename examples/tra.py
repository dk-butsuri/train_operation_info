import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("tra",))
    await tracker.refresh()
    for line in tracker.tra.lines:
        print(line.name, line.status.value, line.updated_at)
        for alert in line.alerts:
            print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
