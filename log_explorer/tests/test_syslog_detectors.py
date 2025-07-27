import pytest

from log_explorer.inference.syslog_detectors import (
    SyslogDetector,
    SystemdJournalDetector,
)
from log_explorer.inference.log_core import LogFormat


@pytest.fixture
def rfc3164_sample():
    return [
        "<34>Oct 11 22:14:15 mymachine su: 'su root' failed for lonvick on /dev/pts/8",
        "<13>Feb  5 17:32:18 host123 sshd[1001]: Accepted password for user from 192.168.0.1",
    ]


@pytest.fixture
def rfc5424_sample():
    return [
        '<34>1 2023-07-27T18:50:00Z mymachine app 12345 ID47 [exampleSDID@32473 iut="3"] BOMAn application event log entry...',
        "<13>1 2023-07-27T20:00:00Z anotherhost nginx 5678 - - [meta info] Request completed",
    ]


@pytest.fixture
def systemd_sample():
    return [
        "_PID=1234",
        "_UID=1000",
        "_GID=1000",
        "PRIORITY=6",
        "__REALTIME_TIMESTAMP=1658936400000000",
        "MESSAGE=Service started",
        "",
        "_PID=5678",
        "_UID=1001",
        "_GID=1001",
        "PRIORITY=5",
        "__REALTIME_TIMESTAMP=1658936500000000",
        "MESSAGE=Service stopped",
        "",
    ]


def test_syslog_detector_rfc3164(rfc3164_sample):
    detector = SyslogDetector()
    result = detector.detect(rfc3164_sample)
    assert result.format_type == LogFormat.SYSLOG
    assert result.confidence > 0.0
    assert "hostname" in result.schema
    assert "message" in result.schema
    assert result.metadata["rfc3164_matches"] > 0


def test_syslog_detector_rfc5424(rfc5424_sample):
    detector = SyslogDetector()
    result = detector.detect(rfc5424_sample)
    assert result.format_type == LogFormat.SYSLOG
    assert result.confidence > 0.0
    assert "app_name" in result.schema
    assert "message" in result.schema
    assert result.metadata["rfc5424_matches"] > 0


def test_systemd_journal_detector(systemd_sample):
    detector = SystemdJournalDetector()
    result = detector.detect(systemd_sample)
    assert result.format_type == LogFormat.SYSTEMD_JOURNAL
    assert result.confidence > 0.0
    assert "__REALTIME_TIMESTAMP" in result.schema
    assert "PRIORITY" in result.schema
    assert result.metadata["journal_entries"] == 2
