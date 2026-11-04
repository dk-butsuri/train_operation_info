import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("kaohsiung_metro",))
    await tracker.refresh()
    for line in tracker.kaohsiung_metro.lines:
        print(line.name, line.scope.value, line.status.value, line.source_status)
        for alert in line.alerts:
            print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
