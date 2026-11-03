import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("odakyu",))
    await tracker.refresh()
    for line in tracker.odakyu.lines:
        print(line.name, line.status.value, line.updated_at)
    for alert in tracker.odakyu.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
