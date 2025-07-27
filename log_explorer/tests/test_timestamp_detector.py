import pytest
from datetime import datetime
from log_explorer.inference.timestamp_detector import TimestampDetector


@pytest.mark.parametrize(
    "text,expected_format",
    [
        ("2023-07-27T14:30:00.123456Z", "%Y-%m-%dT%H:%M:%S.%fZ"),  # iso8601_utc_ms
        ("2023-07-27T14:30:00Z", "%Y-%m-%dT%H:%M:%SZ"),  # iso8601_utc
        ("2023-07-27T14:30:00+02:00", "%Y-%m-%dT%H:%M:%S%z"),  # iso8601_tz
        ("Thu, 27 Jul 2023 14:30:00 +0000", "%a, %d %b %Y %H:%M:%S %z"),  # rfc2822
        ("27/Jul/2023:14:30:00 +0000", "%d/%b/%Y:%H:%M:%S %z"),  # apache_common
        ("2023-07-27 14:30:00,123", "%Y-%m-%d %H:%M:%S,%f"),  # python_logging
        ("2023/07/27 14:30:00", "%Y/%m/%d %H:%M:%S"),  # slash_datetime
        ("07/27/2023 14:30:00", "%m/%d/%Y %H:%M:%S"),  # us_slash_datetime
        ("1689871234", "unix_timestamp"),  # 10-digit Unix seconds
        ("1689871234567", "unix_timestamp_ms"),  # 13-digit Unix ms
        ("1689871234567890", "unix_timestamp_us"),  # 16-digit Unix us
    ],
)
def test_detect_known_timestamp_formats(text, expected_format):
    result = TimestampDetector.get_best_timestamp(text)
    assert result is not None
    dt, fmt, conf = result
    assert fmt == expected_format
    assert isinstance(dt, datetime)
    assert conf > 0.5


@pytest.mark.parametrize(
    "text,pattern_name",
    [
        ("2023-07-27T14:30:00Z", "iso8601_utc"),
        ("1689871234", "unix_seconds"),
        ("07/27/2023 14:30:00", "us_slash_datetime"),
        ("2023-07-27 14:30:00,123", "python_logging"),
    ],
)
def test_confidence_explanation_output(text, pattern_name):
    result = TimestampDetector.get_best_timestamp(text)
    assert result is not None
    _, _, conf = result
    explanation = TimestampDetector.get_confidence_explanation(
        timestamp_str=text, confidence=conf, pattern_name=pattern_name
    )
    assert "confidence" in explanation.lower()
    assert any(
        word in explanation
        for word in ["ISO", "Unix", "US format", "timezone", "precision"]
    )


def test_extract_all_with_confidence_threshold():
    text = (
        "Start: 2023-07-27T10:00:00Z, "
        "End: 2023-07-27T14:30:00.123456Z, "
        "Logged: 1689871234"
    )
    results = TimestampDetector.extract_all_timestamps(text, min_confidence=0.7)
    assert len(results) >= 2
    for dt, fmt, conf in results:
        assert isinstance(dt, datetime)
        assert conf >= 0.7


def test_detect_multiple_and_sorting():
    text = "Logged: 1689871234 and 2023-07-27T14:30:00.123456Z"
    results = TimestampDetector.detect_timestamp(text)
    assert len(results) >= 2
    assert results[0][2] >= results[1][2]  # Sorted by confidence descending


def test_no_match_returns_none():
    text = "completely random string"
    assert TimestampDetector.get_best_timestamp(text) is None
    assert TimestampDetector.extract_all_timestamps(text) == []
