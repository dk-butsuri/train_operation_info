import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("sapporo_subway",))
    await tracker.refresh()
    for line in tracker.sapporo_subway.lines:
        print(line.name, line.status, line.updated_at)
        for alert in line.alerts:
            print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
