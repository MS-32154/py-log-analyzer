import pytest

from log_explorer.inference.app_log_detectors import (
    BaseLogDetector,
    PythonLogDetector,
    BasicLogDetector,
    CustomDelimitedDetector,
    DelimiterAnalysis,
)
from log_explorer.inference.log_core import LogFormat, FormatDetectionResult


@pytest.fixture
def sample_log_lines():
    return [
        "INFO Something happened",
        "DEBUG Debug message",
        "WARNING Possible issue",
        "ERROR Failure occurred",
        "CRITICAL System crash",
    ]


@pytest.fixture
def mock_pattern():
    class MockPattern:
        def __init__(self, name="mock_pattern"):
            self.name = name
            self.pattern = self

        def match(self, line):
            return (
                MockMatch()
                if any(
                    w in line for w in ["INFO", "DEBUG", "ERROR", "CRITICAL", "WARNING"]
                )
                else None
            )

    class MockMatch:
        def group(self, i):
            return "INFO"

    return MockPattern()


def test_base_log_detector(monkeypatch, sample_log_lines, mock_pattern):
    import log_explorer.inference.line_patterns as line_patterns
    import log_explorer.inference.utils as utils

    monkeypatch.setitem(line_patterns.patterns, "TestKey", [mock_pattern])
    monkeypatch.setattr(
        utils.PatternMatcher, "match_patterns", lambda line, patterns, schema: True
    )

    detector = BaseLogDetector("TestKey", LogFormat.BASIC_LOG)
    result = detector.detect(sample_log_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.BASIC_LOG
    assert result.confidence > 0
    assert result.metadata["matches"] == len(sample_log_lines)


def test_python_log_detector(monkeypatch, sample_log_lines, mock_pattern):
    import log_explorer.inference.line_patterns as line_patterns
    import log_explorer.inference.utils as utils

    monkeypatch.setitem(line_patterns.patterns, "PythonLogDetector", [mock_pattern])
    monkeypatch.setattr(
        utils.PatternMatcher, "_extract_schema_from_match", lambda p, m, s: s
    )

    detector = PythonLogDetector()
    result = detector.detect(sample_log_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.PYTHON_LOG
    assert result.confidence > 0
    assert result.metadata["matches"] == len(sample_log_lines)


def test_basic_log_detector(monkeypatch, sample_log_lines, mock_pattern):
    import log_explorer.inference.line_patterns as line_patterns
    import log_explorer.inference.utils as utils

    monkeypatch.setitem(line_patterns.patterns, "BasicLogDetector", [mock_pattern])
    monkeypatch.setattr(
        utils.PatternMatcher, "_extract_schema_from_match", lambda p, m, s: s
    )

    detector = BasicLogDetector()
    result = detector.detect(sample_log_lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.BASIC_LOG
    assert result.confidence > 0
    assert result.metadata["matches"] == len(sample_log_lines)


def test_custom_delimited_detector():
    lines = ["alpha|beta|gamma", "one|two|three", "red|green|blue"]

    detector = CustomDelimitedDetector(delimiters=["|"])
    result = detector.detect(lines)

    assert isinstance(result, FormatDetectionResult)
    assert result.format_type == LogFormat.CUSTOM_DELIMITED
    assert result.confidence > 0
    assert result.schema
    assert "field_1" in result.schema


def test_delimiter_analysis_computation():
    analysis = DelimiterAnalysis("|")
    lines = ["a|b|c", "d|e|f", "g|h|i"]

    for line in lines:
        fields = line.split("|")
        analysis.add_line(line, fields)

    assert analysis.has_data()
    assert analysis.consistent_line_count == 3
    assert analysis.avg_field_count == 3
    assert analysis.field_count_variance == 0
