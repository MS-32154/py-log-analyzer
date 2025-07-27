from datetime import datetime

from .base_parser import PatternBasedParser
from inference.log_core import LogFormat
from inference.line_patterns import patterns


class WebLogParser(PatternBasedParser):

    def _setup_parser(self):
        if self.format_type in [
            LogFormat.APACHE_COMMON,
            LogFormat.APACHE_COMBINED,
            LogFormat.APACHE_EXTENDED,
        ]:
            self.patterns = patterns["ApacheDetector"]
            if self.format_type == LogFormat.APACHE_EXTENDED:
                self.patterns.extend(patterns["ApacheDetector_EXTENDED"])
        elif self.format_type in [LogFormat.NGINX_ACCESS, LogFormat.NGINX_ERROR]:
            self.patterns = patterns["NginxDetector"]
            if self.format_type == LogFormat.NGINX_ACCESS:
                self.patterns.extend(patterns["NginxDetector_ACCESS_ALT"])
            else:
                self.patterns.extend(patterns["NginxDetector_ERROR_ALT"])
        else:
            self.patterns = patterns["GenericWebLogDetector"]

    def _try_pattern(self, line, pattern, entry):
        if not super()._try_pattern(line, pattern, entry):
            return False

        # Parse timestamps with format-specific logic
        if "timestamp" in entry.fields:
            self._parse_web_timestamp(entry)

        # Parse request field if present
        if "request" in entry.fields:
            self._parse_request_field(entry)

        return True

    def _parse_web_timestamp(self, entry):
        timestamp_str = entry.fields["timestamp"]

        try:
            if self.format_type in [LogFormat.NGINX_ERROR]:
                # Nginx error: 2023/12/25 10:15:35
                entry.timestamp = datetime.strptime(timestamp_str, "%Y/%m/%d %H:%M:%S")
            elif "[" in timestamp_str:
                # Apache/Nginx access: [25/Dec/2023:10:15:30 +0000]
                clean_timestamp = timestamp_str.strip("[]").split()[0]
                entry.timestamp = datetime.strptime(
                    clean_timestamp, "%d/%b/%Y:%H:%M:%S"
                )
            else:
                # Fallback to detector
                detected = self.timestamp_detector.detect_timestamp(timestamp_str)
                if detected:
                    entry.timestamp = detected[0][0]
                else:
                    entry.add_parse_error(f"Failed to parse timestamp: {timestamp_str}")
        except ValueError:
            detected = self.timestamp_detector.detect_timestamp(timestamp_str)
            if detected:
                entry.timestamp = detected[0][0]
            else:
                entry.add_parse_error(f"Failed to parse timestamp: {timestamp_str}")

    def _parse_request_field(self, entry):
        request = entry.fields.get("request", "")
        if not request or request == "-":
            return

        try:
            parts = request.split()
            if len(parts) >= 2:
                if "method" in self.schema:
                    entry.fields["method"] = parts[0]
                if "path" in self.schema:
                    entry.fields["path"] = parts[1]
                if "protocol" in self.schema and len(parts) >= 3:
                    entry.fields["protocol"] = parts[2]
        except Exception:
            pass
