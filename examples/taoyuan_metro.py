import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("taoyuan_metro",))
    await tracker.refresh()
    line = tracker.taoyuan_metro.airport
    print(line.name, line.status.value, line.source_status)
    for alert in line.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
