import asyncio

from train_operation_info import Tracker


async def main() -> None:
    # Every refresh downloads the national NeTEx archive as well as the alerts.
    tracker = Tracker(enabled_providers=("tgv",), rate_limit=120)
    await tracker.refresh()
    line = tracker.tgv.network
    print(line.name, line.status)
    for alert in line.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
