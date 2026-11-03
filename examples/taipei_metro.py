import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("taipei_metro",))
    await tracker.refresh()
    for line in tracker.taipei_metro.lines:
        print(line.name, line.operator.name, line.status.value, line.source_status, line.updated_at)
    for alert in tracker.taipei_metro.alerts:
        print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
