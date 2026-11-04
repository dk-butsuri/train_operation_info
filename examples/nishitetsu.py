import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("nishitetsu",))
    await tracker.refresh()
    for line in tracker.nishitetsu.lines:
        print(line.name, line.status)
    for alert in tracker.nishitetsu.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
