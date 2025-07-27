import re
from typing import List
from dataclasses import dataclass


@dataclass
class LogPattern:
    """Represents a log pattern with its regex and field names."""

    pattern: re.Pattern
    field_names: List[str]
    name: str


patterns = {
    "PythonLogDetector": [
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[([^\]]+)\]\s+([^\s]+)\s+-\s+(.*)"
            ),
            field_names=["timestamp", "level", "logger", "message"],
            name="bracketed_format",
        ),
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+([A-Z]+)\s+([^\s]+)\s+(.*)"
            ),
            field_names=["timestamp", "level", "logger", "message"],
            name="simple_format",
        ),
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-\s*([^-]+)\s*-\s*(\w+)\s*-\s*(.*)$"
            ),
            field_names=["timestamp", "logger", "level", "message"],
            name="default_format",
        ),
        LogPattern(
            pattern=re.compile(r"^\[([^\]]+)\]\s+(\w+)\s+in\s+([^:]+):\s*(.*)$"),
            field_names=["timestamp", "level", "logger", "message"],
            name="bracket_in_format",
        ),
        LogPattern(
            pattern=re.compile(
                r"^([^:]+\d{2}:\d{2}:\d{2}[^:]*)\s+(\w+)\s+([^:]+):\s*(.*)$"
            ),
            field_names=["timestamp", "level", "logger", "message"],
            name="timestamped_simple_format",
        ),
        LogPattern(
            pattern=re.compile(r"^(\w+):([^:]+):(.*)$"),
            field_names=["level", "logger", "message"],
            name="simple_no_timestamp",
        ),
    ],
    "BasicLogDetector": [
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\[([^\]]+)\]\s+([^\s]+)\s+-\s+(.*)"
            ),
            field_names=["timestamp", "level", "module", "message"],
            name="bracketed_format",
        ),
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+([A-Z]+)\s+([^\s]+):\s+(.*)"
            ),
            field_names=["timestamp", "level", "module", "message"],
            name="colon_format",
        ),
        LogPattern(
            pattern=re.compile(r"^([^:]+\d{2}:\d{2}:\d{2}[^:]*)\s+(\w+)\s+(.*)"),
            field_names=["timestamp", "level", "message"],
            name="timestamp_level_pattern",
        ),
        LogPattern(
            pattern=re.compile(r"^([^:]+\d{2}:\d{2}:\d{2}[^:]*)\s+(.*)"),
            field_names=["timestamp", "message"],
            name="timestamp_message_pattern",
        ),
        LogPattern(
            pattern=re.compile(r"^(\w+):\s*(.*)"),
            field_names=["level", "message"],
            name="level_message_pattern",
        ),
    ],
    "KeyValueDetector": [
        LogPattern(
            pattern=re.compile(r"(\w+)=([^\s,;]+)"), field_names=[], name="key=value"
        ),
        LogPattern(
            pattern=re.compile(r"(\w+):\s*([^\s,;]+)"),
            field_names=[],
            name="key: value",
        ),
        LogPattern(
            pattern=re.compile(r'(\w+)\s*=\s*"([^"]*)"'),
            field_names=[],
            name='key="value"',
        ),
        LogPattern(
            pattern=re.compile(r"(\w+)=\'([^\']*)\'"),
            field_names=[],
            name="key='value'",
        ),
        LogPattern(
            pattern=re.compile(r"(\w+)\s*:\s*\"([^\"]*)\""),
            field_names=[],
            name='key: "value"',
        ),
    ],
    "SyslogDetector": [
        LogPattern(
            pattern=re.compile(
                r"^<(?P<priority>\d+)>"
                r"(?P<timestamp>[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
                r"(?P<hostname>\S+)\s+"
                r"(?P<tag>[^:]+):\s*"
                r"(?P<message>.*)$"
            ),
            field_names=["priority", "timestamp", "hostname", "tag", "message"],
            name="RFC3164",
        ),
        LogPattern(
            pattern=re.compile(
                r"^<(?P<priority>\d+)>"
                r"(?P<version>\d+)\s+"
                r"(?P<timestamp>\S+)\s+"
                r"(?P<hostname>\S+)\s+"
                r"(?P<app_name>\S+)\s+"
                r"(?P<procid>\S+)\s+"
                r"(?P<msgid>\S+)\s+"
                r"(?:(?P<structured_data>\S+)\s+)?"
                r"(?P<message>.*)$"
            ),
            field_names=[
                "priority",
                "version",
                "timestamp",
                "hostname",
                "app_name",
                "procid",
                "msgid",
                "structured_data",
                "message",
            ],
            name="RFC5424",
        ),
    ],
    "ApacheDetector": [
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'
            ),
            field_names=[
                "remote_host",
                "remote_logname",
                "remote_user",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
            ],
            name="common",
        ),
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)\s+"([^"]*)"\s+"([^"]*)"'
            ),
            field_names=[
                "remote_host",
                "remote_logname",
                "remote_user",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
                "referer",
                "user_agent",
            ],
            name="combined",
        ),
    ],
    "ApacheDetector_EXTENDED": [
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'
            ),
            field_names=[
                "remote_host",
                "remote_logname",
                "remote_user",
                "virtual_host",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
            ],
            name="with_virtual_host",
        ),
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)\s+(\d+|\-)'
            ),
            field_names=[
                "remote_host",
                "remote_logname",
                "remote_user",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
                "response_time",
            ],
            name="with_response_time",
        ),
        LogPattern(
            pattern=re.compile(
                r"^\[([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\]\s+\[([^\]]+)\]\s+(.*)$"
            ),
            field_names=[
                "timestamp",
                "level",
                "message",
            ],
            name="mod_jk",
        ),
    ],
    "NginxDetector": [
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)\s+"([^"]*)"\s+"([^"]*)"'
            ),
            field_names=[
                "remote_addr",
                "remote_logname",
                "remote_user",
                "time_local",
                "request",
                "status",
                "bytes_sent",
                "http_referer",
                "http_user_agent",
            ],
            name="access",
        ),
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(\d+)#(\d+):\s+(.*)"
            ),
            field_names=[
                "timestamp",
                "level",
                "pid",
                "tid",
                "message",
            ],
            name="error",
        ),
    ],
    "NginxDetector_ACCESS_ALT": [
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)\s+"([^"]*)"\s+"([^"]*)"\s+([0-9.]+)'
            ),
            field_names=[
                "remote_addr",
                "remote_logname",
                "remote_user",
                "time_local",
                "request",
                "status",
                "bytes_sent",
                "http_referer",
                "http_user_agent",
                "request_time",
            ],
            name="with_request_time",
        ),
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'
            ),
            field_names=[
                "remote_addr",
                "time_local",
                "request",
                "status",
                "bytes_sent",
            ],
            name="simplified_format",
        ),
    ],
    "NginxDetector_ERROR_ALT": [
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(\d+)#(\d+):\s+\*(\d+)\s+(.*)"
            ),
            field_names=[
                "timestamp",
                "level",
                "pid",
                "tid",
                "connection",
                "message",
            ],
            name="with_connection",
        ),
        LogPattern(
            pattern=re.compile(
                r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(.*)"
            ),
            field_names=[
                "timestamp",
                "level",
                "message",
            ],
            name="simplified_error_format",
        ),
    ],
    "GenericWebLogDetector": [
        LogPattern(
            pattern=re.compile(
                r'^(\S+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'
            ),
            field_names=[
                "remote_addr",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
            ],
            name="ip_dash_dash_timestamp_request",
        ),
        LogPattern(
            pattern=re.compile(r'^(\S+)\s+\[([^\]]+)\]\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'),
            field_names=[
                "remote_addr",
                "timestamp",
                "request",
                "status",
                "bytes_sent",
            ],
            name="ip_timestamp_request",
        ),
        LogPattern(
            pattern=re.compile(r'^\[([^\]]+)\]\s+(\S+)\s+"([^"]*?)"\s+(\d+)\s+(\d+|-)'),
            field_names=[
                "timestamp",
                "remote_addr",
                "request",
                "status",
                "bytes_sent",
            ],
            name="timestamp_ip_request",
        ),
    ],
}
