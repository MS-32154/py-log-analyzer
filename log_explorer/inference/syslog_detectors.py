import re
from dataclasses import dataclass

from .line_patterns import patterns
from .base_detector import BaseFormatDetector
from .log_core import LogFormat, FormatDetectionResult
from .utils import SchemaManager
import logging

logger = logging.getLogger(__name__)


@dataclass
class SyslogMatch:
    """Data class to hold syslog match information."""

    priority: str
    timestamp: str
    hostname: str
    tag: str
    message: str
    version: str = None
    app_name: str = None
    procid: str = None
    msgid: str = None
    structured_data: str = None


class SyslogDetector(BaseFormatDetector):
    """Detector for Syslog format supporting both RFC 3164 and RFC 5424."""

    INTEGER_FIELDS = {"priority", "version"}
    TIMESTAMP_FIELDS = {"timestamp"}

    def __init__(self):
        super().__init__()
        self.patterns = patterns["SyslogDetector"]

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        rfc3164_matches = 0
        rfc5424_matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                match_result = self._try_match_line(line)
                if match_result:
                    match_type, match_data = match_result
                    if match_type == "RFC3164":
                        rfc3164_matches += 1
                    else:
                        rfc5424_matches += 1

                    sample_lines.append(line)
                    self._update_schema_from_match(match_data, schema)
            except Exception as e:
                logger.debug(f"Error processing syslog line: {e}")
                continue

        total_matches = rfc3164_matches + rfc5424_matches
        confidence = self.calculate_line_coverage(total_matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=LogFormat.SYSLOG,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines[:5],
            metadata={
                "rfc3164_matches": rfc3164_matches,
                "rfc5424_matches": rfc5424_matches,
                "detected_rfc": (
                    "RFC3164" if rfc3164_matches >= rfc5424_matches else "RFC5424"
                ),
                "total_lines_processed": len(processed_lines),
            },
        )

    def _try_match_line(self, line):
        for pattern in self.patterns:
            match = pattern.pattern.match(line)
            if match:
                if pattern.name == "RFC3164":
                    return "RFC3164", SyslogMatch(
                        priority=match.group("priority"),
                        timestamp=match.group("timestamp"),
                        hostname=match.group("hostname"),
                        tag=match.group("tag"),
                        message=match.group("message"),
                    )
                elif pattern.name == "RFC5424":
                    return "RFC5424", SyslogMatch(
                        priority=match.group("priority"),
                        timestamp=match.group("timestamp"),
                        hostname=match.group("hostname"),
                        tag="",
                        message=match.group("message"),
                        version=match.group("version"),
                        app_name=match.group("app_name"),
                        procid=match.group("procid"),
                        msgid=match.group("msgid"),
                        structured_data=(
                            match.group("structured_data")
                            if "structured_data" in match.groupdict()
                            else None
                        ),
                    )
        return None

    def _update_schema_from_match(self, match_data, schema):
        fields = {
            "priority": match_data.priority,
            "timestamp": match_data.timestamp,
            "hostname": match_data.hostname,
            "message": match_data.message,
        }

        if match_data.version is None:
            fields["tag"] = match_data.tag
        else:
            fields.update(
                {
                    "version": match_data.version,
                    "app_name": match_data.app_name,
                    "procid": match_data.procid,
                    "msgid": match_data.msgid,
                    "structured_data": match_data.structured_data,
                }
            )

        for field_name, value in fields.items():
            if value:
                data_type = "integer" if field_name in self.INTEGER_FIELDS else None
                is_timestamp = field_name in self.TIMESTAMP_FIELDS
                SchemaManager.update_field_info(
                    schema, field_name, value, data_type, is_timestamp
                )

    def get_confidence_threshold(self):
        return 0.7


class SystemdJournalDetector(BaseFormatDetector):

    FIELD_NAME_PATTERN = re.compile(r"^[_A-Z][A-Z0-9_]*$")
    INTEGER_FIELDS = {
        "_PID",
        "_UID",
        "_GID",
        "PRIORITY",
        "EXIT_STATUS",
        "__REALTIME_TIMESTAMP",
        "__MONOTONIC_TIMESTAMP",
        "SOURCE_REALTIME_TIMESTAMP",
    }
    TIMESTAMP_FIELDS = {
        "__REALTIME_TIMESTAMP",
        "__MONOTONIC_TIMESTAMP",
        "SOURCE_REALTIME_TIMESTAMP",
    }

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines, max_lines=200)
        entries = self._parse_journal_entries(processed_lines)
        schema = self._build_schema_from_entries(entries)
        confidence = self._calculate_journal_confidence(entries, processed_lines)

        return FormatDetectionResult(
            format_type=LogFormat.SYSTEMD_JOURNAL,
            confidence=confidence,
            schema=schema,
            sample_lines=[str(entry) for entry in entries[:5]],
            metadata={
                "journal_entries": len(entries),
                "total_lines_processed": len(processed_lines),
            },
        )

    def preprocess_lines(self, lines, max_lines=200):
        """Override to preserve empty lines for journal entry separation."""
        processed = []
        for i, line in enumerate(lines):
            if i >= max_lines:
                break
            processed.append(line.strip())
        return processed

    def _parse_journal_entries(self, lines):
        entries = []
        current_entry = {}

        for line in lines:
            if not line.strip():
                if current_entry:
                    entries.append(current_entry)
                    current_entry = {}
                continue

            parsed_field = self._parse_journal_field(line)
            if parsed_field:
                key, value = parsed_field
                current_entry[key] = value

        if current_entry:
            entries.append(current_entry)

        return entries

    def _parse_journal_field(self, line):
        if "=" not in line:
            return None

        try:
            key, value = line.split("=", 1)
            if self._is_valid_journal_field(key):
                return key, value
        except ValueError:
            pass

        return None

    def _is_valid_journal_field(self, field_name):
        return bool(field_name and self.FIELD_NAME_PATTERN.match(field_name))

    def _build_schema_from_entries(self, entries):
        schema = {}
        for entry in entries:
            for field_name, value in entry.items():
                data_type = None
                if field_name in self.INTEGER_FIELDS or "TIMESTAMP" in field_name:
                    data_type = "integer"

                is_timestamp = (
                    field_name in self.TIMESTAMP_FIELDS or "TIME" in field_name
                )
                SchemaManager.update_field_info(
                    schema, field_name, value, data_type, is_timestamp
                )

        return schema

    def _calculate_journal_confidence(self, entries, processed_lines):
        """Calculate confidence score for journal format detection."""
        if not entries:
            return 0.0

        expected_lines_per_entry = max(len(processed_lines) / 10, 1)
        confidence = min(len(entries) / expected_lines_per_entry, 1.0)
        return confidence

    def get_confidence_threshold(self):
        return 0.6
