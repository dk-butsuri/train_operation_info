import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("keio",))
    await tracker.refresh()
    for line in tracker.keio.lines:
        print(line.name, line.status.value, line.updated_at)
    for alert in tracker.keio.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
