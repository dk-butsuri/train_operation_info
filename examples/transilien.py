import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("transilien",))
    await tracker.refresh()
    for line in (tracker.transilien.rer_c, tracker.transilien.metro_6,
                 tracker.transilien.metro_3bis, tracker.transilien.metro_7bis):
        print(line.name, line.operator.name, line.status)
        for alert in line.alerts:
            print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
