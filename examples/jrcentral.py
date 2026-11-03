import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("jrcentral",))
    await tracker.refresh()
    for line in tracker.jrcentral.lines:
        print(line.name, line.status.value)
    for alert in tracker.jrcentral.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
