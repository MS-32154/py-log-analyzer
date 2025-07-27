import re

from .base_parser import BaseParser, ParsedLogEntry
from inference.line_patterns import patterns
from inference.timestamp_detector import TimestampDetector


class BaseLogParserMixin:
    def _setup_timestamp_detector(self):
        self.timestamp_detector = TimestampDetector()

    def _try_pattern_match(self, line, pattern, entry):
        match = pattern.pattern.match(line)
        if not match:
            return False

        # Map matched groups to field names
        for i, field_name in enumerate(pattern.field_names, 1):
            if i <= len(match.groups()):
                value = match.group(i).strip()
                self._map_field_value(entry, field_name, value)

        return True

    def _map_field_value(self, entry, field_name, value):
        if field_name not in self.schema:
            return

        if field_name == "timestamp":
            entry.fields[field_name] = value
            detected = self.timestamp_detector.detect_timestamp(value)
            if detected:
                entry.timestamp = detected[0][0]
            else:
                entry.add_parse_error(f"Failed to parse timestamp: {value}")
        else:
            entry.fields[field_name] = self._convert_field_value(field_name, value)

    def _extract_timestamp_from_line(self, line, entry):
        detected_timestamp = self.timestamp_detector.detect_timestamp(line)
        if detected_timestamp:
            entry.timestamp = detected_timestamp[0][0]
            if "timestamp" in self.schema:
                entry.fields["timestamp"] = line

    def _extract_log_level(self, line, entry):
        level_pattern = re.compile(
            r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE
        )
        level_match = level_pattern.search(line)
        if level_match and "level" in self.schema:
            entry.fields["level"] = level_match.group().upper()

    def _store_message(self, line, entry):
        if "message" in self.schema:
            entry.fields["message"] = line


class PythonLogParser(BaseParser, BaseLogParserMixin):
    def _setup_parser(self):
        self._setup_timestamp_detector()
        self.patterns = patterns["PythonLogDetector"]

    def parse_line(self, line, line_number=None):
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            # Try each pattern in order
            for pattern in self.patterns:
                if self._try_pattern_match(line, pattern, entry):
                    return entry

            # Fallback parsing
            self._fallback_parsing(line, entry, "Python log")

        except Exception as e:
            entry.add_parse_error(f"Python log parsing error: {e}")

        return entry

    def _fallback_parsing(self, line, entry, log_type):
        entry.add_parse_error(
            f"No matching {log_type} pattern found - using fallback parsing"
        )

        self._extract_timestamp_from_line(line, entry)
        self._extract_log_level(line, entry)
        self._store_message(line, entry)


class BasicLogParser(BaseParser, BaseLogParserMixin):
    VALID_LOG_LEVELS = {
        "DEBUG",
        "INFO",
        "WARNING",
        "WARN",
        "ERROR",
        "CRITICAL",
        "FATAL",
    }

    def _setup_parser(self):
        self._setup_timestamp_detector()
        self.patterns = patterns["BasicLogDetector"]

    def parse_line(self, line, line_number=None):
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            # Try each pattern in order
            for pattern in self.patterns:
                if self._try_pattern_with_validation(line, pattern, entry):
                    return entry

            # Fallback - treat entire line as message
            self._fallback_parsing(line, entry, "basic log")

        except Exception as e:
            entry.add_parse_error(f"Basic log parsing error: {e}")

        return entry

    def _try_pattern_with_validation(self, line, pattern, entry):
        match = pattern.pattern.match(line)
        if not match:
            return False

        # Special handling for level_message_pattern - validate log level
        if pattern.name == "level_message_pattern":
            level = match.group(1)
            if level.upper() not in self.VALID_LOG_LEVELS:
                return False

        # Map matched groups to field names
        for i, field_name in enumerate(pattern.field_names, 1):
            if i <= len(match.groups()):
                value = match.group(i).strip()
                self._map_field_value(entry, field_name, value)

        return True

    def _fallback_parsing(self, line, entry, log_type):
        entry.add_parse_error(
            f"No matching {log_type} pattern found - treating as plain message"
        )

        self._extract_timestamp_from_line(line, entry)
        self._store_message(line, entry)


class CustomDelimitedParser(BaseParser):

    DEFAULT_DELIMITERS = ["|", ";", "\t", ",", ":", " "]

    def _setup_parser(self):
        self.timestamp_detector = TimestampDetector()
        self.delimiter = self._detect_delimiter()
        self.field_names = list(self.schema.keys())

    def _detect_delimiter(self):
        if (
            hasattr(self, "detection_result")
            and self.detection_result.metadata
            and "delimiter" in self.detection_result.metadata
        ):
            return self.detection_result.metadata["delimiter"]

        # Fallback to detection from sample lines
        if (
            not hasattr(self, "detection_result")
            or not self.detection_result.sample_lines
        ):
            return "|"  # Default fallback

        return self._choose_best_delimiter(self.detection_result.sample_lines[0])

    def _choose_best_delimiter(self, sample_line):
        delimiter_scores = {}
        expected_fields = len(self.field_names)

        for delimiter in self.DEFAULT_DELIMITERS:
            count = sample_line.count(delimiter)
            field_count = count + 1
            score = count * (1.0 / (1 + abs(field_count - expected_fields)))
            delimiter_scores[delimiter] = score

        return max(delimiter_scores.items(), key=lambda x: x[1])[0]

    def parse_line(self, line, line_number=None):
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            parts = line.split(self.delimiter)
            self._map_parts_to_fields(parts, entry)
            self._check_for_extra_parts(parts, entry)
            self._fallback_timestamp_detection(parts, entry)

        except Exception as e:
            entry.add_parse_error(f"Custom delimited parsing error: {e}")

        return entry

    def _map_parts_to_fields(self, parts, entry):
        for i, field_name in enumerate(self.field_names):
            if i < len(parts):
                raw_value = parts[i].strip()
                if field_name in self.schema:
                    self._process_field_value(entry, field_name, raw_value)
            else:
                entry.add_parse_error(f'Missing value for field "{field_name}"')

    def _process_field_value(self, entry, field_name, raw_value):
        if self.schema[field_name].is_timestamp:
            entry.fields[field_name] = raw_value
            detected = self.timestamp_detector.detect_timestamp(raw_value)
            if detected:
                entry.timestamp = detected[0][0]
            else:
                entry.add_parse_error(
                    f"Failed to parse custom delimited timestamp: {raw_value}"
                )
        else:
            entry.fields[field_name] = self._convert_field_value(field_name, raw_value)

    def _check_for_extra_parts(self, parts, entry):
        if len(parts) > len(self.field_names):
            extra_count = len(parts) - len(self.field_names)
            entry.add_parse_error(
                f"Extra values found: {extra_count} more than expected"
            )

    def _fallback_timestamp_detection(self, parts, entry):
        if not entry.timestamp:
            for value in parts:
                detected = self.timestamp_detector.detect_timestamp(value.strip())
                if detected:
                    entry.timestamp = detected[0][0]
                    break
