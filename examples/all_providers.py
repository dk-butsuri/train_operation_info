import asyncio

import httpx

from train_operation_info.exceptions import RefreshError
from train_operation_info import Tracker


async def main() -> None:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        tracker = Tracker(client=client)
        try:
            await tracker.refresh()
        except RefreshError as exc:
            for identifier, error in exc.errors.items():
                print(f"{identifier}: {error}")
        for provider in tracker.providers:
            print(
                provider.provider_id, f"lines={len(provider.lines)}",
                f"delayed={len(provider.delay_lines)}",
                f"affected={len(provider.affected_lines)}",
                f"unknown={len(provider.unknown_lines)}",
            )
        for alert in tracker.alerts:
            print(alert.title)


if __name__ == "__main__":
    asyncio.run(main())
