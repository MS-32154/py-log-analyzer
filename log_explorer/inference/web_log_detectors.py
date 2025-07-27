import logging
from .line_patterns import patterns
from .base_detector import BaseFormatDetector
from .log_core import LogFormat, FormatDetectionResult, FieldInfo
from .utils import DataTypeInferrer
from .timestamp_detector import TimestampDetector

logger = logging.getLogger(__name__)


class WebLogDetectorMixin:
    def _update_field_schema(self, schema, field_name, value, data_type=None):
        if not value or value == "-":
            return

        if field_name not in schema:
            if data_type is None:
                if field_name in (
                    "status",
                    "bytes_sent",
                    "pid",
                    "tid",
                    "response_size",
                ):
                    data_type = "integer"
                elif field_name in ("request_time", "response_time"):
                    data_type = "float"
                else:
                    data_type = DataTypeInferrer.infer_string_type(value)

            is_timestamp = (
                field_name
                in ("timestamp", "time_local", "time_iso8601", "time", "datetime")
                or "time" in field_name.lower()
                or "date" in field_name.lower()
            )

            schema[field_name] = FieldInfo(
                name=field_name, data_type=data_type, is_timestamp=is_timestamp
            )

        field_info = schema[field_name]
        field_info.update_frequency()
        field_info.add_sample_value(value)

        if field_info.is_timestamp:
            timestamps = TimestampDetector.detect_timestamp(value)
            if timestamps:
                best_timestamp = timestamps[0]
                field_info.timestamp_format = best_timestamp[1]
                field_info.confidence = best_timestamp[2]

    def _calculate_format_confidence(self, matches, total_lines, consistency_bonus=0.1):
        base_confidence = self.calculate_line_coverage(matches, total_lines)
        if matches > 0 and total_lines > 0:
            consistency = matches / total_lines
            if consistency > 0.8:
                base_confidence += consistency_bonus
        return min(base_confidence, 1.0)

    def _try_pattern_match(self, line, log_pattern, schema, sample_lines):
        match = log_pattern.pattern.match(line)
        if match:
            if len(sample_lines) < 5:
                sample_lines.append(line)
            groups = match.groups()
            for i, field_name in enumerate(log_pattern.field_names):
                if i < len(groups) and groups[i] and groups[i] not in ("-", ""):
                    self._update_field_schema(schema, field_name, groups[i])
            return True
        return False

    def _create_empty_result(self):
        return FormatDetectionResult(
            format_type=LogFormat.UNKNOWN,
            confidence=0.0,
            schema={},
            sample_lines=[],
            metadata={"error": "No lines to process"},
        )


class ApacheDetector(BaseFormatDetector, WebLogDetectorMixin):
    def __init__(self):
        super().__init__()
        self.common_pattern = patterns["ApacheDetector"][0]
        self.combined_pattern = patterns["ApacheDetector"][1]
        self.extended_patterns = patterns["ApacheDetector_EXTENDED"]

    def detect(self, lines):
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return self._create_empty_result()

        common_matches = 0
        combined_matches = 0
        extended_matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                # Combined format first (more specific)
                if self._try_pattern_match(
                    line, self.combined_pattern, schema, sample_lines
                ):
                    combined_matches += 1
                elif self._try_pattern_match(
                    line, self.common_pattern, schema, sample_lines
                ):
                    common_matches += 1
                elif self._try_extended_patterns(line, schema, sample_lines):
                    extended_matches += 1
            except Exception as e:
                logger.debug(f"Error processing Apache log line: {e}")
                continue

        total_matches = common_matches + combined_matches + extended_matches
        confidence = self._calculate_format_confidence(
            total_matches, len(processed_lines)
        )
        format_type = self._determine_apache_format(
            common_matches, combined_matches, extended_matches
        )

        return FormatDetectionResult(
            format_type=format_type,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines[:5],
            metadata={
                "common_matches": common_matches,
                "combined_matches": combined_matches,
                "extended_matches": extended_matches,
                "total_processed_lines": len(processed_lines),
            },
        )

    def _try_extended_patterns(self, line, schema, sample_lines):
        for pattern in self.extended_patterns:
            if self._try_pattern_match(line, pattern, schema, sample_lines):
                return True
        return False

    def _determine_apache_format(self, common, combined, extended):
        if combined > max(common, extended):
            return LogFormat.APACHE_COMBINED
        elif extended > max(common, combined):
            return LogFormat.APACHE_EXTENDED
        else:
            return LogFormat.APACHE_COMMON

    def get_confidence_threshold(self):
        return 0.7


class NginxDetector(BaseFormatDetector, WebLogDetectorMixin):
    def __init__(self):
        super().__init__()
        self.access_pattern = patterns["NginxDetector"][0]
        self.error_pattern = patterns["NginxDetector"][1]
        self.access_alt_patterns = patterns["NginxDetector_ACCESS_ALT"]
        self.error_alt_patterns = patterns["NginxDetector_ERROR_ALT"]

    def detect(self, lines):
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return self._create_empty_result()

        access_matches = 0
        error_matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                if self._try_patterns(
                    line,
                    [self.access_pattern] + self.access_alt_patterns,
                    schema,
                    sample_lines,
                ):
                    access_matches += 1
                elif self._try_patterns(
                    line,
                    [self.error_pattern] + self.error_alt_patterns,
                    schema,
                    sample_lines,
                ):
                    error_matches += 1
            except Exception as e:
                logger.debug(f"Error processing Nginx log line: {e}")
                continue

        total_matches = access_matches + error_matches
        confidence = self._calculate_format_confidence(
            total_matches, len(processed_lines)
        )
        format_type = (
            LogFormat.NGINX_ACCESS
            if access_matches >= error_matches
            else LogFormat.NGINX_ERROR
        )

        return FormatDetectionResult(
            format_type=format_type,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines[:5],
            metadata={
                "access_matches": access_matches,
                "error_matches": error_matches,
                "total_processed_lines": len(processed_lines),
            },
        )

    def _try_patterns(self, line, pattern_list, schema, sample_lines):
        for pattern in pattern_list:
            if self._try_pattern_match(line, pattern, schema, sample_lines):
                return True
        return False

    def get_confidence_threshold(self):
        return 0.7


class GenericWebLogDetector(BaseFormatDetector, WebLogDetectorMixin):
    def __init__(self):
        super().__init__()
        self.generic_patterns = patterns["GenericWebLogDetector"]

    def detect(self, lines):
        processed_lines = self.preprocess_lines(lines)
        if not processed_lines:
            return self._create_empty_result()

        total_matches = 0
        schema = {}
        sample_lines = []

        for line in processed_lines:
            try:
                for pattern in self.generic_patterns:
                    if self._try_pattern_match(line, pattern, schema, sample_lines):
                        total_matches += 1
                        break
            except Exception as e:
                logger.debug(f"Error processing generic web log line: {e}")
                continue

        confidence = self._calculate_format_confidence(
            total_matches, len(processed_lines)
        )

        return FormatDetectionResult(
            format_type=LogFormat.BASIC_LOG,
            confidence=confidence,
            schema=schema,
            sample_lines=sample_lines[:5],
            metadata={
                "generic_matches": total_matches,
                "total_processed_lines": len(processed_lines),
            },
        )

    def get_confidence_threshold(self):
        return 0.6
