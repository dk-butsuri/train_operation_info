import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("metro_north",))
    await tracker.refresh()
    for line in tracker.metro_north.lines:
        print(line.name, line.status)
        for alert in line.alerts:
            print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
