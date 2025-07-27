import pytest
from log_explorer.inference.web_log_detectors import (
    ApacheDetector,
    NginxDetector,
    GenericWebLogDetector,
)
from log_explorer.inference.log_core import LogFormat


def test_apache_detector_common_log():
    lines = [
        '127.0.0.1 - frank [10/Oct/2020:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
    ]
    detector = ApacheDetector()
    result = detector.detect(lines)

    assert (
        result.format_type == LogFormat.APACHE_COMMON
        or result.format_type == LogFormat.APACHE_COMBINED
    )
    assert result.confidence > 0.5
    assert "timestamp" in result.schema or any(
        f.is_timestamp for f in result.schema.values()
    )
    assert result.sample_lines


def test_nginx_detector_access_log():
    lines = [
        '127.0.0.1 - - [10/Oct/2020:13:55:36 +0000] "GET /index.html HTTP/1.1" 200 1024 "-" "Mozilla/5.0"'
    ]
    detector = NginxDetector()
    result = detector.detect(lines)

    assert result.format_type == LogFormat.NGINX_ACCESS
    assert result.confidence > 0.5
    assert result.sample_lines


def test_empty_input_returns_low_confidence():
    detector = ApacheDetector()
    result = detector.detect([])

    assert result.confidence == 0.0
    assert result.format_type == LogFormat.UNKNOWN
    assert "error" in result.metadata
