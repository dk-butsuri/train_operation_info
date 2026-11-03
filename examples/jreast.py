import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("jreast",))
    await tracker.refresh()
    for line in tracker.jreast.lines:
        print(line.name, line.status.value, line.updated_at)
    for alert in tracker.jreast.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
