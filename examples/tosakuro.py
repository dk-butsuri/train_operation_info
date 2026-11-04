import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("tosakuro",))
    await tracker.refresh()
    for line in tracker.tosakuro.lines:
        print(line.name, line.status, line.source_status)
        for alert in line.alerts:
            print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
