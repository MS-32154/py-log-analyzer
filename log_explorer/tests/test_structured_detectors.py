import pytest

from log_explorer.inference.structured_detectors import (
    JSONDetector,
    CSVDetector,
    LTSVDetector,
    KeyValueDetector,
)
from log_explorer.inference.log_core import LogFormat, FormatDetectionResult


@pytest.fixture
def json_lines():
    return [
        '{"level": "INFO", "msg": "Something happened"}',
        '{"level": "ERROR", "msg": "Failure"}',
        '{"level": "DEBUG", "msg": "Details here"}',
    ]


@pytest.fixture
def csv_lines():
    return [
        "name,age,city",
        "Alice,30,New York",
        "Bob,25,London",
        "Charlie,35,Sydney",
    ]


@pytest.fixture
def ltsv_lines():
    return [
        "host:127.0.0.1\tuser:john\ttime:10/Jul/2023:22:14:19",
        "host:192.168.0.1\tuser:jane\ttime:11/Jul/2023:11:22:33",
        "host:10.0.0.2\tuser:bob\ttime:12/Jul/2023:09:18:00",
    ]


@pytest.fixture
def kv_lines():
    return [
        'user="john" status="ok" code="200"',
        'user="alice" status="error" code="500"',
        'user="bob" status="ok" code="200"',
    ]


def test_json_detector(json_lines):
    detector = JSONDetector()
    result = detector.detect(json_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.JSON
    assert result.confidence > 0
    assert "level" in result.schema
    assert "msg" in result.schema
    assert result.metadata["total_json_lines"] == len(json_lines)


def test_csv_detector(csv_lines):
    detector = CSVDetector()
    result = detector.detect(csv_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.CSV
    assert result.confidence > 0
    assert "name" in result.schema
    assert "age" in result.schema
    assert result.metadata["delimiter"] == ","


def test_ltsv_detector(ltsv_lines):
    detector = LTSVDetector()
    result = detector.detect(ltsv_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.LTSV
    assert result.confidence > 0
    assert "host" in result.schema
    assert "user" in result.schema
    assert result.metadata["ltsv_matches"] == len(ltsv_lines)


def test_key_value_detector(kv_lines, monkeypatch):
    import re

    mock_pattern = re.compile(r'(\w+)="([^"]+)"')
    monkeypatch.setitem(
        __import__(
            "log_explorer.inference.line_patterns", fromlist=["patterns"]
        ).patterns,
        "KeyValueDetector",
        [type("MockPattern", (), {"pattern": mock_pattern})()],
    )

    detector = KeyValueDetector()
    result = detector.detect(kv_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.KEY_VALUE
    assert result.confidence > 0
    assert "user" in result.schema
    assert "status" in result.schema
    assert "code" in result.schema
    assert result.metadata["kv_matches"] == len(kv_lines)
