"""Applicability derived only from a provider's verified current status field.

No notice text, cause, date or publication window is accepted as input. See
tests/fixtures/ALERT_CLASSIFICATION.md for source fields and scope exclusions.
"""

from train_operation_info.models import AlertTiming, LineStatus


def timing_from_status(status: LineStatus) -> AlertTiming:
    """Use only with an explicit source status, before aggregating notices."""
    if status in (LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION):
        return AlertTiming.ACTIVE
    return AlertTiming.UNKNOWN
