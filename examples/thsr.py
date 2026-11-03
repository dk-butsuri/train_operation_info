import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("thsr",))
    await tracker.refresh()
    line = tracker.thsr.main
    print(line.name, line.operator.name, line.status.value)
    print("Source update:", line.updated_at)
    for alert in line.alerts:
        print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
