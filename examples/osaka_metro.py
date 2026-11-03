import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("osaka_metro",))
    await tracker.refresh()

    line = tracker.osaka_metro.midosuji
    print(line.name, line.operator.name, line.status.value)
    print("Source time:", line.updated_at)
    for alert in line.alerts:
        print(alert.title)

    print("Delayed:", [line.name for line in tracker.delay_lines])
    print("Affected:", [line.name for line in tracker.affected_lines])
    print("Unknown:", [line.name for line in tracker.unknown_lines])


if __name__ == "__main__":
    asyncio.run(main())
