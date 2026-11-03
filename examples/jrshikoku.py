import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("jrshikoku",))
    await tracker.refresh()
    for line in tracker.jrshikoku.lines:
        print(line.name, line.status, line.updated_at)
    for alert in tracker.jrshikoku.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
