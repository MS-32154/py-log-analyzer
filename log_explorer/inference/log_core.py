from enum import Enum
from dataclasses import dataclass, field


class LogFormat(Enum):
    JSON = "json"
    SYSLOG = "syslog"
    APACHE_COMMON = "apache_common"
    APACHE_COMBINED = "apache_combined"
    APACHE_EXTENDED = "apache_extended"
    NGINX_ACCESS = "nginx_access"
    NGINX_ERROR = "nginx_error"
    CSV = "csv"
    KEY_VALUE = "key_value"
    SYSTEMD_JOURNAL = "systemd_journal"
    CUSTOM_DELIMITED = "custom_delimited"
    BASIC_LOG = "basic_log"
    PYTHON_LOG = "python_log"
    LTSV = "ltsv"
    UNKNOWN = "unknown"


@dataclass
class FieldInfo:

    name: str
    data_type: str
    is_timestamp: bool = False
    timestamp_format: str = None
    sample_values: list = field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.0

    def add_sample_value(self, value, max_samples=10):
        if len(self.sample_values) < max_samples and value not in self.sample_values:
            self.sample_values.append(value)

    def update_frequency(self):
        self.frequency += 1


@dataclass
class FormatDetectionResult:

    format_type: LogFormat
    confidence: float
    schema: dict
    sample_lines: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_sample_line(self, line, max_samples=5):
        if len(self.sample_lines) < max_samples:
            self.sample_lines.append(line)

    def update_field_schema(
        self, field_name, value, data_type="string", is_timestamp=False
    ):
        if field_name not in self.schema:
            self.schema[field_name] = FieldInfo(
                name=field_name, data_type=data_type, is_timestamp=is_timestamp
            )

        field_info = self.schema[field_name]
        field_info.update_frequency()
        field_info.add_sample_value(value)

        return field_info
