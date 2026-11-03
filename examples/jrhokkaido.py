import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("jrhokkaido",))
    await tracker.refresh()
    for line in tracker.jrhokkaido.lines:
        print(line.name, line.status.value, line.updated_at)
    for alert in tracker.jrhokkaido.alerts:
        print(alert.title, alert.description)


if __name__ == "__main__":
    asyncio.run(main())
