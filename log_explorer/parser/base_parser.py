from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from log_explorer.inference.timestamp_detector import TimestampDetector


@dataclass
class ParsedLogEntry:
    fields: dict
    raw_line: str
    line_number: int = None
    timestamp: datetime = None
    is_malformed: bool = False
    parse_errors: list = field(default_factory=list)
    confidence: float = 1.0

    def add_parse_error(self, error):
        self.parse_errors.append(error)
        self.is_malformed = True
        self.confidence = max(0.1, 1.0 - (len(self.parse_errors) * 0.2))


@dataclass
class ParseResult:
    entries: list
    total_lines: int
    successfully_parsed: int
    malformed_lines: int
    parse_statistics: dict = field(default_factory=dict)

    @property
    def success_rate(self):
        return (
            self.successfully_parsed / self.total_lines if self.total_lines > 0 else 0.0
        )


class BaseParser(ABC):
    def __init__(self, detection_result):
        self.detection_result = detection_result
        self.schema = detection_result.schema
        self.format_type = detection_result.format_type
        self.timestamp_detector = TimestampDetector()
        self._setup_parser()

    @abstractmethod
    def _setup_parser(self):
        pass

    @abstractmethod
    def parse_line(self, line, line_number=None):
        pass

    def parse_lines(self, lines):
        entries = []
        successfully_parsed = 0
        malformed_lines = 0

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue

            entry = self.parse_line(line.strip(), i)
            entries.append(entry)

            if entry.is_malformed:
                malformed_lines += 1
            else:
                successfully_parsed += 1

        return ParseResult(
            entries=entries,
            total_lines=len([l for l in lines if l.strip()]),
            successfully_parsed=successfully_parsed,
            malformed_lines=malformed_lines,
            parse_statistics=self._calculate_statistics(entries),
        )

    def _calculate_statistics(self, entries):
        if not entries:
            return {}

        field_stats = {}
        for field_name in self.schema.keys():
            extracted_count = sum(1 for entry in entries if field_name in entry.fields)
            field_stats[field_name] = {
                "extraction_rate": extracted_count / len(entries),
                "total_extracted": extracted_count,
            }

        error_counts = {}
        for entry in entries:
            for error in entry.parse_errors:
                error_type = self._classify_error(error)
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

        return {
            "field_extraction_rates": field_stats,
            "average_confidence": sum(e.confidence for e in entries) / len(entries),
            "error_types": error_counts,
        }

    def _classify_error(self, error):
        error_lower = error.lower()
        if "timestamp" in error_lower:
            return "timestamp_parsing"
        elif "field" in error_lower:
            return "field_extraction"
        elif "format" in error_lower:
            return "format_mismatch"
        elif "type" in error_lower:
            return "type_conversion"
        else:
            return "other"

    def _convert_field_value(self, field_name, value):
        if field_name not in self.schema:
            return value

        field_info = self.schema[field_name]
        data_type = field_info.data_type.lower()

        try:
            if data_type == "integer":
                return int(value)
            elif data_type == "float":
                return float(value)
            elif data_type == "boolean":
                return value.lower() in ("true", "1", "yes", "on")
            else:
                return value
        except (ValueError, TypeError):
            return value

    def _extract_timestamp_from_entry(self, entry):
        for field_name, value in entry.fields.items():
            if isinstance(value, str):
                detected = self.timestamp_detector.detect_timestamp(value)
                if detected:
                    return detected[0][0]
        return None

    def _map_field_value(self, entry, field_name, value):
        if field_name in self.schema:
            if field_name == "timestamp":
                entry.fields[field_name] = value
                detected = self.timestamp_detector.detect_timestamp(value)
                if detected:
                    entry.timestamp = detected[0][0]
                else:
                    entry.add_parse_error(f"Failed to parse timestamp: {value}")
            else:
                entry.fields[field_name] = self._convert_field_value(field_name, value)


class PatternBasedParser(BaseParser):
    def __init__(self, detection_result):
        self.patterns = []
        super().__init__(detection_result)

    def _setup_parser(self):
        pass

    def parse_line(self, line, line_number=None):
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            for pattern in self.patterns:
                if self._try_pattern(line, pattern, entry):
                    return entry
            self._fallback_parsing(line, entry)
        except Exception as e:
            entry.add_parse_error(f"Parsing error: {e}")

        return entry

    def _try_pattern(self, line, pattern, entry):
        match = pattern.pattern.match(line)
        if not match:
            return False

        for i, field_name in enumerate(pattern.field_names, 1):
            if i <= len(match.groups()):
                value = match.group(i).strip()
                self._map_field_value(entry, field_name, value)

        return True

    def _fallback_parsing(self, line, entry):
        entry.add_parse_error("No matching pattern found - using fallback parsing")

        detected = self.timestamp_detector.detect_timestamp(line)
        if detected:
            entry.timestamp = detected[0][0]
            if "timestamp" in self.schema:
                entry.fields["timestamp"] = line

        if "message" in self.schema:
            entry.fields["message"] = line
