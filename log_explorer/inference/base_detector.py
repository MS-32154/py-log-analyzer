from abc import ABC, abstractmethod

from .log_core import FormatDetectionResult


class BaseFormatDetector(ABC):

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def detect(self, lines) -> FormatDetectionResult:
        """Detect format and extract schema information."""
        pass

    @abstractmethod
    def get_confidence_threshold(self) -> float:
        """Return minimum confidence threshold for this detector."""
        pass

    def preprocess_lines(self, lines, max_lines=100):
        """Preprocess lines before analysis."""
        processed = []
        for i, line in enumerate(lines):
            if i >= max_lines:
                break
            line = line.strip()
            if line:
                processed.append(line)
        return processed

    def calculate_line_coverage(self, matches, total_lines):
        """Calculate what percentage of lines matched this format."""
        return matches / total_lines if total_lines > 0 else 0.0
