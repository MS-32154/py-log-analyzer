from pathlib import Path
import logging

from .structured_parsers import JSONParser, DelimitedParser, KeyValueParser
from .web_log_parsers import WebLogParser
from .syslog_parsers import (
    SyslogParser,
    SystemdJournalParser,
    BaseParser,
    ParsedLogEntry,
)
from .base_parser import PatternBasedParser, ParseResult
from inference.log_core import LogFormat
from inference.line_patterns import patterns
from inference.utils import CompressionHandler

logger = logging.getLogger(__name__)


class LogParsingEngine:
    def __init__(self):
        self.parser_classes = {
            LogFormat.JSON: JSONParser,
            LogFormat.CSV: DelimitedParser,
            LogFormat.LTSV: KeyValueParser,
            LogFormat.KEY_VALUE: KeyValueParser,
            LogFormat.APACHE_COMMON: WebLogParser,
            LogFormat.APACHE_COMBINED: WebLogParser,
            LogFormat.APACHE_EXTENDED: WebLogParser,
            LogFormat.NGINX_ACCESS: WebLogParser,
            LogFormat.NGINX_ERROR: WebLogParser,
            LogFormat.SYSLOG: SyslogParser,
            LogFormat.SYSTEMD_JOURNAL: SystemdJournalParser,
            LogFormat.PYTHON_LOG: PatternBasedParser,
            LogFormat.BASIC_LOG: PatternBasedParser,
            LogFormat.CUSTOM_DELIMITED: DelimitedParser,
        }
        logger.info(
            f"Initialized parsing engine with {len(self.parser_classes)} parser types"
        )

    def create_parser(self, detection_result) -> BaseParser:
        format_type = detection_result.format_type

        if format_type == LogFormat.UNKNOWN:
            raise ValueError("Cannot create parser for unknown format")

        if format_type not in self.parser_classes:
            raise ValueError(f"No parser available for format: {format_type.value}")

        parser_class = self.parser_classes[format_type]
        parser = parser_class(detection_result)

        # For pattern-based parsers, set up patterns after instantiation
        if isinstance(parser, PatternBasedParser):
            if format_type == LogFormat.PYTHON_LOG:
                parser.patterns = patterns["PythonLogDetector"]
            elif format_type == LogFormat.BASIC_LOG:
                parser.patterns = patterns["BasicLogDetector"]

        logger.info(f"Created {parser_class.__name__} for format {format_type.value}")
        return parser

    def parse_file(self, filepath, detection_result) -> ParseResult:
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        parser = self.create_parser(detection_result)

        lines = []
        try:
            for line in CompressionHandler.open_file(filepath):
                lines.append(line.rstrip("\n\r"))
            logger.info(f"Read {len(lines)} lines from {filepath}")
        except Exception as e:
            logger.error(f"Error reading file {filepath}: {e}")
            raise

        result = parser.parse_lines(lines)
        result.parse_statistics.update(
            {
                "source_file": str(filepath),
                "file_size_bytes": filepath.stat().st_size,
                "format_detection_confidence": detection_result.confidence,
            }
        )

        logger.info(
            f"Parsed {result.successfully_parsed}/{result.total_lines} lines "
            f"({result.success_rate:.1%} success rate)"
        )
        return result

    def parse_lines(self, lines, detection_result) -> ParseResult:
        parser = self.create_parser(detection_result)
        result = parser.parse_lines(lines)
        result.parse_statistics.update(
            {"format_detection_confidence": detection_result.confidence}
        )
        return result

    def parse_single_line(self, line, detection_result) -> ParsedLogEntry:
        parser = self.create_parser(detection_result)
        return parser.parse_line(line)

    def get_supported_formats(self):
        return [fmt.value for fmt in self.parser_classes.keys()]

    def validate_parsing_capability(self, detection_result):
        format_type = detection_result.format_type

        validation_result = {
            "can_parse": False,
            "format_type": format_type.value,
            "detection_confidence": detection_result.confidence,
            "estimated_parse_quality": 0.0,
            "warnings": [],
            "field_count": len(detection_result.schema),
        }

        if format_type == LogFormat.UNKNOWN:
            validation_result["warnings"].append("Format is unknown - cannot parse")
            return validation_result

        if format_type not in self.parser_classes:
            validation_result["warnings"].append(
                f"No parser available for format: {format_type.value}"
            )
            return validation_result

        validation_result["can_parse"] = True

        # Estimate parsing quality
        base_quality = detection_result.confidence
        timestamp_fields = sum(
            1 for field in detection_result.schema.values() if field.is_timestamp
        )
        timestamp_bonus = min(timestamp_fields * 0.1, 0.2)
        field_bonus = min(len(detection_result.schema) * 0.05, 0.3)

        sample_penalty = 0.0
        if len(detection_result.sample_lines) < 3:
            sample_penalty = 0.1
            validation_result["warnings"].append(
                "Limited sample size may affect parsing accuracy"
            )

        estimated_quality = min(
            base_quality + timestamp_bonus + field_bonus - sample_penalty, 1.0
        )
        validation_result["estimated_parse_quality"] = estimated_quality

        if estimated_quality < 0.7:
            validation_result["warnings"].append(
                "Low estimated parsing quality - expect parsing errors"
            )

        return validation_result
