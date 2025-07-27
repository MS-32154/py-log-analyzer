from pathlib import Path
import logging

from .log_core import FormatDetectionResult, LogFormat
from .utils import CompressionHandler
from .web_log_detectors import ApacheDetector, NginxDetector, GenericWebLogDetector
from .syslog_detectors import SyslogDetector, SystemdJournalDetector
from .app_log_detectors import (
    PythonLogDetector,
    BasicLogDetector,
    CustomDelimitedDetector,
)
from .structured_detectors import (
    JSONDetector,
    CSVDetector,
    LTSVDetector,
    KeyValueDetector,
)

logger = logging.getLogger(__name__)


class LogSchemaInferenceEngine:

    def __init__(self):
        # Order matters - more specific detectors should come first
        self.detectors = [
            JSONDetector(),
            SyslogDetector(),
            PythonLogDetector(),
            SystemdJournalDetector(),
            ApacheDetector(),
            NginxDetector(),
            CSVDetector(),
            LTSVDetector(),
            GenericWebLogDetector(),
            CustomDelimitedDetector(),
            KeyValueDetector(),
            BasicLogDetector(),
        ]

        logger.info(
            f"Initialized inference engine with {len(self.detectors)} detectors"
        )

    def analyze_file(self, filepath) -> FormatDetectionResult:
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if not filepath.is_file():
            raise ValueError(f"Path is not a file: {filepath}")

        lines = []
        try:
            line_count = 0
            for line in CompressionHandler.open_file(filepath):
                if line_count >= 1000:
                    break
                lines.append(line.rstrip("\n\r"))
                line_count += 1

            logger.info(f"Read {len(lines)} lines from {filepath}")

        except Exception as e:
            logger.error(f"Error reading file {filepath}: {e}")
            raise

        if not lines:
            return FormatDetectionResult(
                format_type=LogFormat.UNKNOWN,
                confidence=0.0,
                schema={},
                metadata={"error": "Empty file", "file_path": str(filepath)},
            )

        return self.analyze_lines(lines)

    def analyze_lines(self, lines) -> FormatDetectionResult:
        if not lines:
            return FormatDetectionResult(
                format_type=LogFormat.UNKNOWN,
                confidence=0.0,
                schema={},
                metadata={"error": "No lines provided"},
            )

        results = []
        detection_errors = []

        for detector in self.detectors:
            try:
                logger.debug(f"Running detector: {detector.name}")
                result = detector.detect(lines)

                if result.confidence >= detector.get_confidence_threshold():
                    results.append(result)
                    logger.debug(f"{detector.name} confidence: {result.confidence:.3f}")
                else:
                    logger.debug(
                        f"{detector.name} below threshold: {result.confidence:.3f} < {detector.get_confidence_threshold()}"
                    )

            except Exception as e:
                error_msg = f"Detector {detector.name} failed: {e}"
                logger.warning(error_msg)
                detection_errors.append(error_msg)

        if not results:
            return FormatDetectionResult(
                format_type=LogFormat.UNKNOWN,
                confidence=0.0,
                schema={},
                sample_lines=lines[:5],
                metadata={
                    "message": "No format detected with sufficient confidence",
                    "detection_errors": detection_errors,
                    "total_lines_analyzed": len(lines),
                },
            )

        best_result = max(results, key=lambda x: x.confidence)

        self._calculate_field_confidence(best_result)

        best_result.metadata.update(
            {
                "total_detectors_run": len(self.detectors),
                "detectors_above_threshold": len(results),
                "detection_errors": detection_errors,
                "total_lines_analyzed": len(lines),
            }
        )

        logger.info(
            f"Best match: {best_result.format_type.value} (confidence: {best_result.confidence:.3f})"
        )

        return best_result

    def _calculate_field_confidence(self, result: FormatDetectionResult):
        if not result.schema:
            return

        total_sample_lines = len(result.sample_lines) if result.sample_lines else 1

        for field_info in result.schema.values():
            frequency_score = min(field_info.frequency / total_sample_lines, 1.0)
            timestamp_bonus = 0.2 if field_info.is_timestamp else 0.0
            type_bonus = 0.1 if field_info.data_type != "unknown" else 0.0

            field_info.confidence = min(
                frequency_score + timestamp_bonus + type_bonus, 1.0
            )

    def get_supported_formats(self):
        return [fmt.value for fmt in LogFormat if fmt != LogFormat.UNKNOWN]

    def get_detector_info(self):
        info = []
        for detector in self.detectors:
            info.append(
                {
                    "name": detector.name,
                    "confidence_threshold": detector.get_confidence_threshold(),
                    "format": getattr(detector, "format_type", "unknown"),
                }
            )
        return info
