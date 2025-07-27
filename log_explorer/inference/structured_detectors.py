import json
import csv
import re
from io import StringIO

from .base_detector import BaseFormatDetector
from .log_core import LogFormat, FormatDetectionResult
from .utils import SchemaManager
from .line_patterns import patterns

import logging

logger = logging.getLogger(__name__)


class JSONDetector(BaseFormatDetector):

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines, max_lines=50)
        if not processed_lines:
            return FormatDetectionResult(LogFormat.JSON, 0.0, {})

        json_count = 0
        schema = {}
        samples = []

        for line in processed_lines:
            try:
                data = json.loads(line)
                json_count += 1
                samples.append(line)
                self._extract_json_schema(data, schema)
                if json_count >= 50:
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        confidence = self.calculate_line_coverage(json_count, len(processed_lines))

        return FormatDetectionResult(
            format_type=LogFormat.JSON,
            confidence=confidence,
            schema=schema,
            sample_lines=samples[:5],
            metadata={"total_json_lines": json_count},
        )

    def _extract_json_schema(self, data, schema):
        if not isinstance(data, dict):
            return

        for key, value in data.items():
            clean_key = str(key).strip()
            if clean_key:
                SchemaManager.update_field_info(schema, clean_key, str(value))

    def get_confidence_threshold(self):
        return 0.8


class CSVDetector(BaseFormatDetector):

    def __init__(self):
        super().__init__()
        self.supported_delimiters = ",;\t|"

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines, max_lines=50)
        if not processed_lines:
            return FormatDetectionResult(LogFormat.CSV, 0.0, {})

        csv_text = "\n".join(processed_lines)

        try:
            dialect_info = self._detect_csv_dialect(csv_text)
            if not dialect_info:
                return FormatDetectionResult(LogFormat.CSV, 0.0, {})

            schema_data = self._parse_csv_content(csv_text, dialect_info["dialect"])

            if not self._is_probably_csv(
                processed_lines, dialect_info["dialect"], schema_data
            ):
                return FormatDetectionResult(LogFormat.CSV, 0.0, {})

            confidence = self._calculate_csv_confidence(
                schema_data, len(processed_lines)
            )

            return FormatDetectionResult(
                format_type=LogFormat.CSV,
                confidence=confidence,
                schema=schema_data["schema"],
                sample_lines=schema_data["samples"][:5],
                metadata={
                    "delimiter": dialect_info["dialect"].delimiter,
                    "has_header": dialect_info["has_header"],
                    "rows_processed": schema_data["rows_processed"],
                },
            )

        except Exception as e:
            logger.debug(f"CSV detection failed: {e}")
            return FormatDetectionResult(LogFormat.CSV, 0.0, {})

    def _detect_csv_dialect(self, csv_text):
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(csv_text, delimiters=self.supported_delimiters)
            has_header = sniffer.has_header(csv_text)
            return {"dialect": dialect, "has_header": has_header}
        except:
            return self._fallback_dialect_detection(csv_text)

    def _fallback_dialect_detection(self, csv_text):
        lines = csv_text.split("\n")[:5]
        if len(lines) < 2:
            return None

        delimiter_counts = {}
        for delimiter in self.supported_delimiters:
            counts = [line.count(delimiter) for line in lines if line.strip()]
            if counts and len(set(counts)) <= 2:
                delimiter_counts[delimiter] = max(counts)

        if not delimiter_counts:
            return None

        best_delimiter = max(delimiter_counts.items(), key=lambda x: x[1])[0]
        dialect = csv.excel()
        dialect.delimiter = best_delimiter

        return {"dialect": dialect, "has_header": True}

    def _parse_csv_content(self, csv_text, dialect):
        try:
            reader = csv.DictReader(StringIO(csv_text), dialect=dialect)
            schema = {}
            samples = []
            rows_processed = 0

            for row in reader:
                if rows_processed >= 50:
                    break
                if not row or not any(str(v).strip() for v in row.values()):
                    continue

                rows_processed += 1
                row_values = [str(v) if v is not None else "" for v in row.values()]
                samples.append(dialect.delimiter.join(row_values))

                for field_name, value in row.items():
                    clean_field_name = str(field_name).strip() if field_name else ""
                    if clean_field_name:
                        SchemaManager.update_field_info(
                            schema, clean_field_name, str(value)
                        )

            return {
                "schema": schema,
                "samples": samples,
                "rows_processed": rows_processed,
            }
        except Exception:
            return {"schema": {}, "samples": [], "rows_processed": 0}

    def _is_probably_csv(self, lines, dialect, schema_data):
        delimiter = dialect.delimiter
        delimiter_lines = sum(1 for line in lines if delimiter in line)

        return (
            delimiter_lines >= max(3, len(lines) // 2)
            and schema_data["rows_processed"] >= 3
        )

    def _calculate_csv_confidence(self, schema_data, total_lines):
        rows_processed = schema_data["rows_processed"]
        if rows_processed == 0:
            return 0.0

        base_confidence = rows_processed / max(total_lines, 1)
        return min(base_confidence + (0.2 if rows_processed >= 3 else 0), 1.0)

    def get_confidence_threshold(self):
        return 0.6


class LTSVDetector(BaseFormatDetector):

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return FormatDetectionResult(LogFormat.LTSV, 0.0, {})

        matches = 0
        schema = {}
        samples = []

        for line in processed_lines:
            if self._is_ltsv_format(line):
                matches += 1
                samples.append(line)
                self._extract_ltsv_schema(line, schema)

        confidence = self.calculate_line_coverage(matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=LogFormat.LTSV,
            confidence=confidence,
            schema=schema,
            sample_lines=samples[:5],
            metadata={"ltsv_matches": matches},
        )

    def _is_ltsv_format(self, line):
        if "\t" not in line:
            return False

        parts = line.split("\t")
        valid_pairs = sum(1 for part in parts if self._is_valid_ltsv_pair(part.strip()))
        return valid_pairs >= 2

    def _is_valid_ltsv_pair(self, part):
        if ":" not in part or "=" in part:
            return False

        try:
            key, value = part.split(":", 1)
            return bool(key.strip() and value.strip())
        except ValueError:
            return False

    def _extract_ltsv_schema(self, line, schema):
        parts = line.split("\t")
        for part in parts:
            part = part.strip()
            if ":" in part:
                try:
                    key, value = part.split(":", 1)
                    key, value = key.strip(), value.strip()
                    if key and value:
                        SchemaManager.update_field_info(schema, key, value)
                except ValueError:
                    continue

    def get_confidence_threshold(self):
        return 0.7


class KeyValueDetector(BaseFormatDetector):

    def __init__(self):
        super().__init__()
        self.kv_patterns = [pattern.pattern for pattern in patterns["KeyValueDetector"]]

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return FormatDetectionResult(LogFormat.KEY_VALUE, 0.0, {})

        matches = 0
        schema = {}
        samples = []

        for line in processed_lines:
            kv_pairs = self._extract_key_value_pairs(line)
            if len(kv_pairs) >= 2:
                matches += 1
                samples.append(line)
                self._update_kv_schema(schema, kv_pairs)

        confidence = self.calculate_line_coverage(matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=LogFormat.KEY_VALUE,
            confidence=confidence,
            schema=schema,
            sample_lines=samples[:5],
            metadata={"kv_matches": matches},
        )

    def _extract_key_value_pairs(self, line):
        kv_pairs = {}
        for pattern in self.kv_patterns:
            try:
                matches = pattern.findall(line)
                for key, value in matches:
                    key, value = key.strip(), value.strip()
                    if key and value:
                        kv_pairs[key] = value
            except re.error:
                continue
        return kv_pairs

    def _update_kv_schema(self, schema, kv_pairs):
        """Update schema with extracted key-value pairs."""
        for key, value in kv_pairs.items():
            SchemaManager.update_field_info(schema, key, value)

    def get_confidence_threshold(self):
        return 0.6
