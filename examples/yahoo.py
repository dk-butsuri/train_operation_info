"""Explicit Yahoo selection; inspect published terms before choosing a source."""

import asyncio

from train_operation_info.providers.yahoo import YahooArea, YahooProvider
from train_operation_info import Tracker


async def main() -> None:
    yahoo = YahooProvider(areas=(YahooArea.KINKI,))
    print(yahoo.metadata.usage_permission.value)
    print(yahoo.metadata.terms_url)
    print(*yahoo.metadata.additional_terms_urls, sep="\n")
    tracker = Tracker(enabled_providers=("yahoo",), overrides=(yahoo,))
    await tracker.refresh()
    for line in tracker.affected_lines:
        print(line.name, line.status.value, line.updated_at)
        for alert in line.alerts:
            print(alert.description)


if __name__ == "__main__":
    asyncio.run(main())
