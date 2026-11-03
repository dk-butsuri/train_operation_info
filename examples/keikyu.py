import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("keikyu",))
    await tracker.refresh()
    for line in tracker.keikyu.lines:
        print(line.name, line.status.value, line.updated_at)
    for alert in tracker.keikyu.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
