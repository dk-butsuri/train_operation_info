import asyncio

from train_operation_info import Tracker


async def main() -> None:
    tracker = Tracker(enabled_providers=("renfe",))
    await tracker.refresh()
    line = tracker.renfe.cercanias
    print("Origen de los datos: Renfe Operadora (CC BY 4.0)")
    print("https://creativecommons.org/licenses/by/4.0/")
    print(line.name, line.status, "Source updated:", line.updated_at)
    for alert in line.alerts:
        print(alert.title, alert.description, sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
