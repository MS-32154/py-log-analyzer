import gzip
import bz2
import lzma

from .timestamp_detector import TimestampDetector
from .log_core import FieldInfo

import logging

logger = logging.getLogger(__name__)


class CompressionHandler:

    COMPRESSION_MAP = {".gz": "gzip", ".bz2": "bz2", ".xz": "xz", ".lzma": "lzma"}

    @classmethod
    def detect_compression(cls, filepath):
        suffix = filepath.suffix.lower()
        return cls.COMPRESSION_MAP.get(suffix)

    @classmethod
    def open_file(cls, filepath):
        compression = cls.detect_compression(filepath)

        try:
            if compression == "gzip":
                with gzip.open(filepath, "rt", encoding="utf-8", errors="ignore") as f:
                    yield from f
            elif compression == "bz2":
                with bz2.open(filepath, "rt", encoding="utf-8", errors="ignore") as f:
                    yield from f
            elif compression in ("xz", "lzma"):
                with lzma.open(filepath, "rt", encoding="utf-8", errors="ignore") as f:
                    yield from f
            else:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    yield from f
        except Exception as e:
            logger.error(f"Error opening file {filepath}: {e}")
            raise


class DataTypeInferrer:

    @staticmethod
    def infer_type(value) -> str:
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return DataTypeInferrer.infer_string_type(value)
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return "unknown"

    @staticmethod
    def infer_string_type(value):
        if not value:
            return "string"

        # Check for boolean values
        if value.lower() in ("true", "false", "yes", "no", "y", "n", "1", "0"):
            return "boolean"

        # Check for numeric values
        try:
            int(value)
            return "integer"
        except ValueError:
            try:
                float(value)
                return "float"
            except ValueError:
                # Check if it could be a timestamp
                if TimestampDetector.detect_timestamp(value):
                    return "timestamp"
                return "string"


class SchemaManager:
    @staticmethod
    def update_field_info(
        schema, field_name, value, data_type=None, is_timestamp_field=False
    ):
        if not value or value == "-":
            return

        if field_name not in schema:
            if data_type is None:
                data_type = DataTypeInferrer.infer_string_type(value)

            schema[field_name] = FieldInfo(
                name=field_name,
                data_type=data_type,
                is_timestamp=is_timestamp_field,
            )

        field_info = schema[field_name]
        field_info.update_frequency()
        field_info.add_sample_value(value)

        if is_timestamp_field or not field_info.is_timestamp:
            timestamps = TimestampDetector.detect_timestamp(value)
            if timestamps:
                field_info.is_timestamp = True
                field_info.timestamp_format = timestamps[0][1]


class PatternMatcher:
    @staticmethod
    def match_patterns(line, patterns, schema):
        for pattern in patterns:
            match = pattern.pattern.match(line)
            if match:
                PatternMatcher._extract_schema_from_match(pattern, match, schema)
                return True
        return False

    @staticmethod
    def _extract_schema_from_match(pattern, match, schema):
        for i, field_name in enumerate(pattern.field_names, 1):
            if i <= len(match.groups()):
                value = match.group(i)
                if value:
                    is_timestamp = field_name in (
                        "timestamp",
                        "time_local",
                        "time_iso8601",
                    )
                    SchemaManager.update_field_info(
                        schema, field_name, value, is_timestamp_field=is_timestamp
                    )
