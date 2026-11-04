import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("fukuoka_subway",))
    await tracker.refresh()
    for line in tracker.fukuoka_subway.lines:
        print(line.name, line.status)
    for alert in tracker.fukuoka_subway.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
