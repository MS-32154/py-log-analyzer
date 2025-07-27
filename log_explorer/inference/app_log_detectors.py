from .line_patterns import patterns
from .base_detector import BaseFormatDetector
from .log_core import LogFormat, FormatDetectionResult, FieldInfo
from .utils import DataTypeInferrer, PatternMatcher
from .timestamp_detector import TimestampDetector

import logging

logger = logging.getLogger(__name__)


class BaseLogDetector(BaseFormatDetector):

    def __init__(self, patterns_key, format_type: LogFormat, threshold=0.7):
        super().__init__()
        self.patterns = patterns[patterns_key]
        self.format_type = format_type
        self.threshold = threshold

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                if PatternMatcher.match_patterns(line, self.patterns, schema):
                    matches += 1
                    if len(sample_lines) < 5:
                        sample_lines.append(line)
            except Exception as e:
                logger.debug(f"Error processing log line: {e}")
                continue

        confidence = self.calculate_line_coverage(matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=self.format_type,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines,
            metadata={"matches": matches, "total_lines": len(processed_lines)},
        )

    def get_confidence_threshold(self):
        return self.threshold


class PythonLogDetector(BaseLogDetector):

    def __init__(self):
        super().__init__("PythonLogDetector", LogFormat.PYTHON_LOG, 0.8)

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                pattern_match = self._find_matching_pattern(line)
                if pattern_match:
                    pattern, match_obj = pattern_match
                    matches += 1
                    if len(sample_lines) < 5:
                        sample_lines.append(line)
                    PatternMatcher._extract_schema_from_match(
                        pattern, match_obj, schema
                    )
            except Exception as e:
                logger.debug(f"Error processing log line: {e}")
                continue

        confidence = self.calculate_line_coverage(matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=self.format_type,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines,
            metadata={"matches": matches, "total_lines": len(processed_lines)},
        )

    def _find_matching_pattern(self, line):
        for pattern in self.patterns:
            match = pattern.pattern.match(line)
            if match:
                # Special validation for simple_no_timestamp pattern
                if pattern.name == "simple_no_timestamp":
                    level = match.group(1)
                    if level.upper() not in [
                        "DEBUG",
                        "INFO",
                        "WARNING",
                        "WARN",
                        "ERROR",
                        "CRITICAL",
                        "FATAL",
                    ]:
                        continue
                return pattern, match
        return None


class BasicLogDetector(BaseLogDetector):

    def __init__(self):
        super().__init__("BasicLogDetector", LogFormat.BASIC_LOG, 0.7)

    def detect(self, lines) -> FormatDetectionResult:
        """Override to add basic log validation."""
        processed_lines = self.preprocess_lines(lines)
        matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                pattern_match = self._find_matching_pattern(line)
                if pattern_match:
                    pattern, match_obj = pattern_match
                    matches += 1
                    if len(sample_lines) < 5:
                        sample_lines.append(line)
                    PatternMatcher._extract_schema_from_match(
                        pattern, match_obj, schema
                    )
            except Exception as e:
                logger.debug(f"Error processing log line: {e}")
                continue

        confidence = self.calculate_line_coverage(matches, len(processed_lines))

        return FormatDetectionResult(
            format_type=self.format_type,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines,
            metadata={"matches": matches, "total_lines": len(processed_lines)},
        )

    def _find_matching_pattern(self, line):
        for pattern in self.patterns:
            match = pattern.pattern.match(line)
            if match:
                # Special validation for level_message_pattern
                if pattern.name == "level_message_pattern":
                    level = match.group(1)
                    if level.upper() not in [
                        "DEBUG",
                        "INFO",
                        "WARNING",
                        "WARN",
                        "ERROR",
                        "CRITICAL",
                        "FATAL",
                    ]:
                        continue
                return pattern, match
        return None


class CustomDelimitedDetector(BaseFormatDetector):

    def __init__(self, delimiters=None, min_fields=2, max_variance_ratio=0.3):
        super().__init__()
        self.delimiters = delimiters or ["|", ";", ":", "\t", "~"]
        self.min_fields = min_fields
        self.max_variance_ratio = max_variance_ratio
        self.confidence_threshold = 0.5

    def detect(self, lines) -> FormatDetectionResult:
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return FormatDetectionResult(LogFormat.CUSTOM_DELIMITED, 0.0, {})

        best_result = None
        best_confidence = 0.0

        for delimiter in self.delimiters:
            result = self._analyze_delimiter(processed_lines, delimiter)
            if result.confidence > best_confidence:
                best_confidence = result.confidence
                best_result = result

        return best_result or FormatDetectionResult(LogFormat.CUSTOM_DELIMITED, 0.0, {})

    def _analyze_delimiter(self, lines, delimiter) -> FormatDetectionResult:
        analysis = DelimiterAnalysis(delimiter)

        for line in lines:
            if delimiter in line:
                fields = [field.strip() for field in line.split(delimiter)]
                if len(fields) >= self.min_fields:
                    analysis.add_line(line, fields)

        if not analysis.has_data():
            return FormatDetectionResult(LogFormat.CUSTOM_DELIMITED, 0.0, {})

        confidence = self._calculate_delimiter_confidence(analysis, len(lines))
        if confidence < self.confidence_threshold:
            return FormatDetectionResult(LogFormat.CUSTOM_DELIMITED, 0.0, {})

        schema = self._build_delimited_schema(analysis)

        return FormatDetectionResult(
            format_type=LogFormat.CUSTOM_DELIMITED,
            confidence=confidence,
            schema=schema,
            sample_lines=analysis.sample_lines[:5],
            metadata={
                "delimiter": delimiter,
                "avg_fields": analysis.avg_field_count,
                "field_count_variance": analysis.field_count_variance,
                "consistent_lines": analysis.consistent_line_count,
            },
        )

    def _calculate_delimiter_confidence(self, analysis, total_lines):
        if not analysis.has_data():
            return 0.0

        coverage_score = analysis.consistent_line_count / total_lines
        variance_ratio = analysis.field_count_variance / max(
            analysis.avg_field_count, 1
        )
        consistency_score = max(0, 1.0 - (variance_ratio / self.max_variance_ratio))
        adequacy_score = min(1.0, analysis.avg_field_count / 4.0)

        weights = [0.5, 0.3, 0.2]
        confidence = (
            weights[0] * coverage_score
            + weights[1] * consistency_score
            + weights[2] * adequacy_score
        )

        return min(1.0, confidence)

    def _build_delimited_schema(self, analysis):
        schema = {}

        for field_idx, field_data in analysis.field_data.items():
            field_name = f"field_{field_idx + 1}"
            data_type = self._infer_field_type(field_data["values"])

            field_info = FieldInfo(
                name=field_name,
                data_type=data_type,
                is_timestamp=field_data["is_timestamp"],
            )

            field_info.frequency = len(field_data["values"])
            field_info.sample_values = list(set(field_data["values"]))[:10]

            if field_data["timestamp_format"]:
                field_info.timestamp_format = field_data["timestamp_format"]

            schema[field_name] = field_info

        return schema

    def _infer_field_type(self, values):
        if not values:
            return "string"

        sample_values = values[:100] if len(values) > 100 else values
        type_counts = {}

        for value in sample_values:
            if value:
                inferred_type = DataTypeInferrer.infer_string_type(value)
                type_counts[inferred_type] = type_counts.get(inferred_type, 0) + 1

        return (
            max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else "string"
        )

    def get_confidence_threshold(self):
        return self.confidence_threshold


class DelimiterAnalysis:

    def __init__(self, delimiter):
        self.delimiter = delimiter
        self.field_counts = []
        self.sample_lines = []
        self.consistent_line_count = 0
        self.field_data = {}

    def add_line(self, line, fields):
        self.field_counts.append(len(fields))
        self.sample_lines.append(line)
        self.consistent_line_count += 1

        for idx, field_value in enumerate(fields):
            if idx not in self.field_data:
                self.field_data[idx] = {
                    "values": [],
                    "is_timestamp": False,
                    "timestamp_format": None,
                }

            field_info = self.field_data[idx]
            field_info["values"].append(field_value)

            if field_value and not field_info["is_timestamp"]:
                timestamps = TimestampDetector.detect_timestamp(field_value)
                if timestamps:
                    field_info["is_timestamp"] = True
                    field_info["timestamp_format"] = timestamps[0][1]

    def has_data(self):
        return self.consistent_line_count > 0

    @property
    def avg_field_count(self):
        return (
            sum(self.field_counts) / len(self.field_counts) if self.field_counts else 0
        )

    @property
    def field_count_variance(self):
        if not self.field_counts:
            return 0

        avg = self.avg_field_count
        return sum((count - avg) ** 2 for count in self.field_counts) / len(
            self.field_counts
        )
