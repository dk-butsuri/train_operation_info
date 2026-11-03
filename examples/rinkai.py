import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("rinkai",))
    await tracker.refresh()
    line = tracker.rinkai.main
    print(line.name, line.status, line.updated_at)
    for alert in line.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
