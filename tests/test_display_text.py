"""Alert text is normalized for direct display; wording is never changed."""

import pytest

from train_operation_info.models import AlertEffect, ServiceAlert, display_text


@pytest.mark.parametrize(("raw", "expected"), [
    # Trailing padding as published by JR Hokkaido titles.
    ("【車両不具合による列車への影響について】" + " " * 100, "【車両不具合による列車への影響について】"),
    # Indentation inside a JR Shikoku heading.
    ("土讃線 車両点検の影響\n\t\t          \t\t          《一部列車の遅れ》", "土讃線 車両点検の影響 《一部列車の遅れ》"),
])
def test_title_is_one_trimmed_line(raw: str, expected: str) -> None:
    assert display_text(raw, single_line=True) == expected


@pytest.mark.parametrize(("raw", "expected"), [
    ("本文。\n\n\n\n", "本文。"),
    (" 一行目 \r\n\r\n\r\n二行目\t\tです ", "一行目\n\n二行目 です"),
    # Ideographic spaces are used for alignment and are kept.
    ("運転再開　　：16:43頃\n　【遅延：折尾　から　直方】", "運転再開　　：16:43頃\n　【遅延：折尾　から　直方】"),
])
def test_description_keeps_paragraphs(raw: str, expected: str) -> None:
    assert display_text(raw) == expected


def test_service_alert_applies_display_text() -> None:
    alert = ServiceAlert(
        alert_id="x", title=" 題名 \n 続き ", description="本文\n\n\n\n終わり \n",
        effect=AlertEffect.OTHER, affected_line_ids=(), source_url="https://example.com/",
    )
    assert alert.title == "題名 続き"
    assert alert.description == "本文\n\n終わり"
