import json
import csv
import re
from io import StringIO

from .base_parser import BaseParser, ParsedLogEntry
from log_explorer.inference.line_patterns import patterns
from log_explorer.inference.log_core import LogFormat


class JSONParser(BaseParser):

    def _setup_parser(self):
        pass

    def parse_line(self, line, line_number=None) -> ParsedLogEntry:
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            json_data = json.loads(line)
            for field_name in self.schema.keys():
                if field_name in json_data:
                    raw_value = json_data[field_name]
                    entry.fields[field_name] = self._convert_field_value(
                        field_name, str(raw_value)
                    )
                else:
                    entry.add_parse_error(
                        f'Expected field "{field_name}" not found in JSON'
                    )

            entry.timestamp = self._extract_timestamp_from_entry(entry)

        except json.JSONDecodeError as e:
            entry.add_parse_error(f"Invalid JSON: {e}")
        except Exception as e:
            entry.add_parse_error(f"Unexpected error parsing JSON: {e}")

        return entry


class DelimitedParser(BaseParser):

    def _setup_parser(self):
        self.field_names = list(self.schema.keys())
        self.delimiter = self._detect_delimiter()

    def _detect_delimiter(self):
        if (
            hasattr(self, "detection_result")
            and self.detection_result.metadata
            and "delimiter" in self.detection_result.metadata
        ):
            return self.detection_result.metadata["delimiter"]

        if (
            not hasattr(self, "detection_result")
            or not self.detection_result.sample_lines
        ):
            return self._get_default_delimiter()

        sample_line = self.detection_result.sample_lines[0]
        delimiters = self._get_delimiter_candidates()
        expected_fields = len(self.field_names)

        delimiter_scores = {}
        for delimiter in delimiters:
            count = sample_line.count(delimiter)
            field_count = count + 1
            score = count * (1.0 / (1 + abs(field_count - expected_fields)))
            delimiter_scores[delimiter] = score

        return max(delimiter_scores.items(), key=lambda x: x[1])[0]

    def _get_delimiter_candidates(self):
        if self.format_type == LogFormat.CSV:
            return [",", ";", "\t", "|"]
        else:
            return ["|", ";", "\t", ",", ":", " "]

    def _get_default_delimiter(self):
        return "," if self.format_type == LogFormat.CSV else "|"

    def parse_line(self, line, line_number=None) -> ParsedLogEntry:
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            if self.format_type == LogFormat.CSV:
                csv_reader = csv.reader(StringIO(line), delimiter=self.delimiter)
                parts = next(csv_reader)
            else:
                parts = line.split(self.delimiter)

            for i, field_name in enumerate(self.field_names):
                if i < len(parts):
                    raw_value = parts[i].strip()
                    if field_name in self.schema:
                        if self.schema[field_name].is_timestamp:
                            entry.fields[field_name] = raw_value
                            detected = self.timestamp_detector.detect_timestamp(
                                raw_value
                            )
                            if detected:
                                entry.timestamp = detected[0][0]
                            else:
                                entry.add_parse_error(
                                    f"Failed to parse timestamp: {raw_value}"
                                )
                        else:
                            entry.fields[field_name] = self._convert_field_value(
                                field_name, raw_value
                            )
                else:
                    entry.add_parse_error(f'Missing value for field "{field_name}"')

            if len(parts) > len(self.field_names):
                entry.add_parse_error(
                    f"Extra values found: {len(parts) - len(self.field_names)} more"
                )

            if not entry.timestamp:
                for value in parts:
                    detected = self.timestamp_detector.detect_timestamp(value.strip())
                    if detected:
                        entry.timestamp = detected[0][0]
                        break

        except Exception as e:
            entry.add_parse_error(f"Delimited parsing error: {e}")

        return entry


class KeyValueParser(BaseParser):

    def _setup_parser(self):
        if self.format_type == LogFormat.LTSV:
            # LTSV: key1:value1<TAB>key2:value2
            self.kv_pattern = re.compile(r"([^:\t]+):([^\t]*)")
        else:
            # General key-value patterns
            self.kv_patterns = [
                pattern.pattern for pattern in patterns["KeyValueDetector"]
            ]

    def parse_line(self, line, line_number=None) -> ParsedLogEntry:
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            found_fields = {}

            if self.format_type == LogFormat.LTSV:
                matches = self.kv_pattern.findall(line)
                for key, value in matches:
                    found_fields[key.strip()] = value.strip()
            else:
                for pattern in self.kv_patterns:
                    matches = pattern.findall(line)
                    for key, value in matches:
                        key, value = key.strip(), value.strip()
                        if key and value:
                            found_fields[key] = value

            if not found_fields:
                entry.add_parse_error("No valid key-value pairs found")
                return entry

            for field_name in self.schema.keys():
                if field_name in found_fields:
                    entry.fields[field_name] = self._convert_field_value(
                        field_name, found_fields[field_name]
                    )
                else:
                    # Try case-insensitive matching
                    found_key = next(
                        (k for k in found_fields if k.lower() == field_name.lower()),
                        None,
                    )
                    if found_key:
                        entry.fields[field_name] = self._convert_field_value(
                            field_name, found_fields[found_key]
                        )
                    else:
                        entry.add_parse_error(
                            f'Expected field "{field_name}" not found'
                        )

            entry.timestamp = self._extract_timestamp_from_entry(entry)

        except Exception as e:
            entry.add_parse_error(f"Key-value parsing error: {e}")

        return entry
