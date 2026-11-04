import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("tfl",))
    await tracker.refresh()
    print("Powered by TfL Open Data")
    for line in tracker.tfl.lines:
        print(line.name, line.status.value, line.source_status)
        for alert in line.alerts:
            print(alert.timing.value, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
