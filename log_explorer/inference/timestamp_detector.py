import re
from datetime import datetime, timezone

from .timestamp_patterns import TIMESTAMP_PATTERNS

import logging

logger = logging.getLogger(__name__)


class TimestampDetector:

    TIMESTAMP_PATTERNS = TIMESTAMP_PATTERNS

    @classmethod
    def detect_timestamp(cls, text):
        """
        Detect timestamps in text and return list of (datetime, format, confidence).

        Args:
            text: Input text to search for timestamps

        Returns:
            List of tuples containing (datetime_object, format_string, confidence_score)
        """
        results = []
        found_positions = set()  # Track positions to avoid overlapping matches

        for pattern_info in cls.TIMESTAMP_PATTERNS:
            pattern = pattern_info["pattern"]
            format_str = pattern_info["format"]

            matches = re.finditer(pattern, text)

            for match in matches:
                # Skip if this position overlaps with a higher-confidence match
                start, end = match.span()
                if any(pos >= start and pos < end for pos in found_positions):
                    continue

                timestamp_str = match.group(0)

                try:
                    # Parse the timestamp
                    parsed_dt, confidence = cls._parse_timestamp(
                        timestamp_str, format_str, pattern_info
                    )

                    if parsed_dt:
                        results.append((parsed_dt, format_str, confidence))
                        # Mark this position range as used
                        found_positions.update(range(start, end))

                except Exception as e:
                    logger.debug(
                        f"Failed to parse timestamp '{timestamp_str}' with format '{format_str}': {e}"
                    )
                    continue

        # Sort by confidence (highest first), then by position in text
        results.sort(key=lambda x: (-x[2], x[0]))
        return results

    @classmethod
    def _parse_timestamp(cls, timestamp_str, format_str, pattern_info):
        """
        Parse a timestamp string with the given format and calculate confidence.

        Returns:
            Tuple of (datetime_object, confidence_score)
        """
        try:
            # Handle special cases first
            if format_str.startswith("unix_timestamp"):
                dt, base_confidence = cls._parse_unix_timestamp(
                    timestamp_str, format_str
                )
            elif format_str.endswith("Z"):
                # Handle ISO 8601 with Z timezone
                dt = datetime.strptime(timestamp_str[:-1], format_str[:-1])
                dt = dt.replace(tzinfo=timezone.utc)
                base_confidence = pattern_info["base_confidence"]
            elif "%z" in format_str:
                # Handle timezone formats
                dt, base_confidence = cls._parse_with_timezone(
                    timestamp_str, format_str, pattern_info
                )
            elif format_str == "apache_modjk_bracketed":
                # Handle bracketed format - remove brackets for parsing
                clean_timestamp = timestamp_str.strip("[]")
                dt = datetime.strptime(clean_timestamp, format_str.strip("[]"))
                base_confidence = pattern_info["base_confidence"]
                # Handle milliseconds in Python logging format
                dt, base_confidence = cls._parse_python_logging_format(
                    timestamp_str, format_str, pattern_info
                )
            elif ",%f" in format_str:
                # Handle microseconds in ISO format
                dt, base_confidence = cls._parse_iso_with_microseconds(
                    timestamp_str, format_str, pattern_info
                )
            else:
                # Standard parsing
                dt = datetime.strptime(timestamp_str, format_str)
                base_confidence = pattern_info["base_confidence"]

            # Calculate final confidence with context adjustments
            final_confidence = cls._calculate_final_confidence(
                base_confidence, timestamp_str, pattern_info, dt
            )

            return dt, final_confidence

        except ValueError as e:
            logger.debug(
                f"Failed to parse '{timestamp_str}' with format '{format_str}': {e}"
            )
            return None, 0.0

    @classmethod
    def _parse_unix_timestamp(cls, timestamp_str, format_str):
        timestamp_int = int(timestamp_str)

        if format_str == "unix_timestamp":
            # Unix seconds - should be between 1970 and ~2100
            if timestamp_int < 0 or timestamp_int > 4000000000:
                raise ValueError("Unix timestamp out of reasonable range")
            dt = datetime.fromtimestamp(timestamp_int, tz=timezone.utc)
            base_confidence = 0.85
        elif format_str == "unix_timestamp_ms":
            # Unix milliseconds
            if timestamp_int < 0 or timestamp_int > 4000000000000:
                raise ValueError("Unix millisecond timestamp out of reasonable range")
            dt = datetime.fromtimestamp(timestamp_int / 1000, tz=timezone.utc)
            base_confidence = 0.80
        elif format_str == "unix_timestamp_us":
            # Unix microseconds
            if timestamp_int < 0 or timestamp_int > 4000000000000000:
                raise ValueError("Unix microsecond timestamp out of reasonable range")
            dt = datetime.fromtimestamp(timestamp_int / 1000000, tz=timezone.utc)
            base_confidence = 0.75
        else:
            raise ValueError(f"Unknown unix timestamp format: {format_str}")

        # Reduce confidence if timestamp is too far in future or past
        years_diff = abs((dt - datetime.now(timezone.utc)).days / 365.25)
        if years_diff > 50:
            base_confidence *= 0.7
        elif years_diff > 10:
            base_confidence *= 0.9

        return dt, base_confidence

    @classmethod
    def _parse_with_timezone(cls, timestamp_str, format_str, pattern_info):
        base_confidence = pattern_info["base_confidence"]

        try:
            dt = datetime.strptime(timestamp_str, format_str)
            return dt, base_confidence
        except ValueError:
            # Try to handle timezone format variations
            if "+0000" in timestamp_str or "-0000" in timestamp_str:
                try:
                    dt = datetime.strptime(timestamp_str, format_str)
                    return dt, base_confidence * 0.95
                except ValueError:
                    pass

            # Parse without timezone as fallback
            tz_pattern = r"[+-]\d{2}:?\d{2}$"
            timestamp_no_tz = re.sub(tz_pattern, "", timestamp_str).strip()
            format_no_tz = format_str.replace(" %z", "").replace("%z", "")

            try:
                dt = datetime.strptime(timestamp_no_tz, format_no_tz)
                return dt, base_confidence * 0.7  # Reduce confidence for naive datetime
            except ValueError:
                raise

    @classmethod
    def _parse_python_logging_format(cls, timestamp_str, format_str, pattern_info):
        base_confidence = pattern_info["base_confidence"]

        # Convert comma to dot for microseconds parsing
        timestamp_with_dot = timestamp_str.replace(",", ".")
        parts = timestamp_with_dot.split(".")

        if len(parts) == 2:
            # Pad milliseconds to microseconds (6 digits)
            microseconds = parts[1].ljust(6, "0")[:6]
            timestamp_with_dot = f"{parts[0]}.{microseconds}"

        format_with_dot = format_str.replace(",%f", ".%f")

        try:
            dt = datetime.strptime(timestamp_with_dot, format_with_dot)
            return dt, base_confidence
        except ValueError:
            # Fallback to parsing without microseconds
            base_timestamp = timestamp_str.split(",")[0]
            base_format = format_str.split(",%f")[0]
            dt = datetime.strptime(base_timestamp, base_format)
            return dt, base_confidence * 0.9

    @classmethod
    def _parse_iso_with_microseconds(cls, timestamp_str, format_str, pattern_info):
        base_confidence = pattern_info["base_confidence"]

        if "." not in timestamp_str:
            dt = datetime.strptime(timestamp_str, format_str.replace(".%f", ""))
            return dt, base_confidence * 0.95

        base_part, remainder = timestamp_str.split(".", 1)

        # Extract timezone if present
        tz_part = ""
        micro_part = remainder

        if remainder.endswith("Z"):
            micro_part = remainder[:-1]
            tz_part = "Z"
        elif "+" in remainder or remainder.count("-") > 0:
            for i, char in enumerate(remainder):
                if char in ["+", "-"]:
                    tz_part = remainder[i:]
                    micro_part = remainder[:i]
                    break

        # Normalize microseconds to 6 digits
        micro_part = micro_part.ljust(6, "0")[:6]
        reconstructed = f"{base_part}.{micro_part}{tz_part}"

        try:
            if tz_part == "Z":
                dt = datetime.strptime(reconstructed[:-1], format_str.replace("Z", ""))
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = datetime.strptime(reconstructed, format_str)
            return dt, base_confidence
        except ValueError:
            # Fallback without microseconds
            dt = datetime.strptime(base_part + tz_part, format_str.replace(".%f", ""))
            return dt, base_confidence * 0.9

    @classmethod
    def _calculate_final_confidence(
        cls, base_confidence, timestamp_str, pattern_info, parsed_dt
    ):
        """
        Calculate final confidence score with contextual adjustments.

        Args:
            base_confidence: Base confidence from pattern
            timestamp_str: Original timestamp string
            pattern_info: Pattern metadata
            parsed_dt: Parsed datetime object

        Returns:
            Final confidence score (0.0 to 1.0)
        """
        confidence = base_confidence

        # Bonus for specificity indicators
        specificity_bonus = {"high": 0.05, "medium": 0.02, "low": 0.0}
        confidence += specificity_bonus.get(pattern_info.get("specificity", "low"), 0.0)

        # Bonus for timezone information
        if pattern_info.get("has_timezone", False):
            confidence += 0.03

        # Bonus for microsecond precision
        if pattern_info.get("has_microseconds", False) and "." in timestamp_str:
            confidence += 0.02

        # Penalty for ambiguous formats (US date formats)
        if pattern_info["name"].startswith("us_"):
            confidence -= 0.05

        # Temporal validity check
        current_time = datetime.now(timezone.utc if parsed_dt.tzinfo else None)
        time_diff = abs((parsed_dt - current_time).total_seconds())

        # Penalty for timestamps too far in the future or past
        if time_diff > 86400 * 365 * 10:  # 10 years
            confidence *= 0.8
        elif time_diff > 86400 * 365 * 50:  # 50 years
            confidence *= 0.6

        # Bonus for reasonable timestamp length
        if 19 <= len(timestamp_str) <= 35:  # Typical full timestamp length
            confidence += 0.02
        elif len(timestamp_str) < 10:  # Very short timestamps are less reliable
            confidence -= 0.05

        # Format consistency check
        if re.search(r"\d{4}", timestamp_str):  # Has 4-digit year
            confidence += 0.01

        # Clamp confidence to valid range
        return max(0.0, min(1.0, confidence))

    @classmethod
    def get_best_timestamp(cls, text):
        """
        Get the best (highest confidence) timestamp from text.

        Returns:
            Tuple of (datetime, format, confidence) or None if no timestamps found
        """
        results = cls.detect_timestamp(text)
        return results[0] if results else None

    @classmethod
    def extract_all_timestamps(cls, text, min_confidence=0.5):
        """
        Extract all timestamps with confidence above threshold.

        Args:
            text: Input text
            min_confidence: Minimum confidence threshold (0.0 to 1.0)

        Returns:
            List of timestamps with confidence >= min_confidence
        """
        results = cls.detect_timestamp(text)
        return [result for result in results if result[2] >= min_confidence]

    @classmethod
    def get_confidence_explanation(cls, timestamp_str, confidence, pattern_name):
        """
        Get a human-readable explanation of the confidence score.

        Args:
            timestamp_str: The timestamp string
            confidence: The confidence score
            pattern_name: The pattern name that matched

        Returns:
            Explanation string
        """
        explanations = []

        if confidence >= 0.9:
            explanations.append("Very high confidence")
        elif confidence >= 0.8:
            explanations.append("High confidence")
        elif confidence >= 0.7:
            explanations.append("Good confidence")
        elif confidence >= 0.6:
            explanations.append("Moderate confidence")
        else:
            explanations.append("Low confidence")

        if "iso8601" in pattern_name:
            explanations.append("ISO 8601 standard format")
        elif "unix" in pattern_name:
            explanations.append("Unix timestamp format")
        elif "us_" in pattern_name:
            explanations.append("US format (potentially ambiguous)")

        if "Z" in timestamp_str or any(
            tz in timestamp_str for tz in ["+", "-", "UTC", "GMT"]
        ):
            explanations.append("includes timezone")

        if "." in timestamp_str and len(timestamp_str.split(".")[-1]) > 2:
            explanations.append("has sub-second precision")

        return " - ".join(explanations)
