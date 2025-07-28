import re
from datetime import datetime

from .base_parser import BaseParser, ParsedLogEntry, PatternBasedParser, ParseResult
from log_explorer.inference.line_patterns import patterns


class SyslogParser(PatternBasedParser):
    def _setup_parser(self):
        self.patterns = patterns["SyslogDetector"]
        self.simple_pattern = re.compile(
            r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$"
        )

    def _try_pattern(self, line, pattern, entry):
        match = pattern.pattern.match(line)
        if not match:
            return False

        if pattern.name in ["RFC3164", "RFC5424"]:
            self._parse_rfc_pattern(match, pattern.name, entry)
        else:
            for i, field_name in enumerate(pattern.field_names, 1):
                if i <= len(match.groups()):
                    value = match.group(i).strip()
                    self._map_field_value(entry, field_name, value)

        return True

    def _parse_rfc_pattern(self, match, rfc_type, entry):
        if rfc_type == "RFC3164":
            field_mapping = {
                "priority": match.group("priority"),
                "timestamp": match.group("timestamp"),
                "hostname": match.group("hostname"),
                "tag": match.group("tag"),
                "message": match.group("message"),
            }
        else:  # RFC5424
            field_mapping = {
                "priority": match.group("priority"),
                "version": match.group("version"),
                "timestamp": match.group("timestamp"),
                "hostname": match.group("hostname"),
                "app_name": match.group("app_name"),
                "procid": match.group("procid"),
                "msgid": match.group("msgid"),
                "message": match.group("message"),
            }

        for field_name, value in field_mapping.items():
            if field_name in self.schema and value:
                if field_name == "timestamp":
                    entry.fields[field_name] = value
                    if rfc_type == "RFC3164":
                        try:
                            current_year = datetime.now().year
                            full_timestamp = f"{current_year} {value}"
                            entry.timestamp = datetime.strptime(
                                full_timestamp, "%Y %b %d %H:%M:%S"
                            )
                        except ValueError:
                            self._map_field_value(entry, field_name, value)
                    else:
                        self._map_field_value(entry, field_name, value)
                else:
                    entry.fields[field_name] = self._convert_field_value(
                        field_name, value
                    )

        if "priority" in field_mapping and field_mapping["priority"]:
            self._extract_facility_severity(int(field_mapping["priority"]), entry)

    def _extract_facility_severity(self, priority, entry):
        facility = priority >> 3
        severity = priority & 0x07

        if "facility" in self.schema:
            entry.fields["facility"] = self._convert_field_value(
                "facility", str(facility)
            )
        if "severity" in self.schema:
            entry.fields["severity"] = self._convert_field_value(
                "severity", str(severity)
            )

    def _fallback_parsing(self, line, entry):
        match = self.simple_pattern.match(line)
        if match:
            timestamp_str, hostname, message = match.groups()
            field_mapping = {
                "timestamp": timestamp_str,
                "hostname": hostname,
                "message": message,
            }

            for field_name, value in field_mapping.items():
                if field_name in self.schema:
                    if field_name == "timestamp":
                        entry.fields[field_name] = value
                        try:
                            current_year = datetime.now().year
                            full_timestamp = f"{current_year} {timestamp_str}"
                            entry.timestamp = datetime.strptime(
                                full_timestamp, "%Y %b %d %H:%M:%S"
                            )
                        except ValueError:
                            self._map_field_value(entry, field_name, value)
                    else:
                        entry.fields[field_name] = self._convert_field_value(
                            field_name, value
                        )
        else:
            super()._fallback_parsing(line, entry)


class SystemdJournalParser(BaseParser):

    def _setup_parser(self):
        self.field_pattern = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")
        self.journalctl_pattern = re.compile(
            r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+([^:]+):\s*(.*)$"
        )

    def parse_lines(self, lines):
        entries = []
        successfully_parsed = 0
        malformed_lines = 0

        journal_entries = self._group_lines_into_entries(lines)

        for entry_lines in journal_entries:
            if not entry_lines:
                continue

            entry = self._parse_journal_entry(entry_lines)
            entries.append(entry)

            if entry.is_malformed:
                malformed_lines += 1
            else:
                successfully_parsed += 1

        return ParseResult(
            entries=entries,
            total_lines=len([l for l in lines if l.strip()]),
            successfully_parsed=successfully_parsed,
            malformed_lines=malformed_lines,
            parse_statistics=self._calculate_statistics(entries),
        )

    def _group_lines_into_entries(self, lines):
        entries = []
        current_entry = []

        for line in lines:
            if not line.strip():
                if current_entry:
                    entries.append(current_entry)
                    current_entry = []
            else:
                current_entry.append(line.strip())

        if current_entry:
            entries.append(current_entry)

        return entries

    def _parse_journal_entry(self, entry_lines):
        raw_line = "\n".join(entry_lines)
        entry = ParsedLogEntry(fields={}, raw_line=raw_line)

        try:
            if len(entry_lines) == 1 and "=" not in entry_lines[0]:
                self._parse_journalctl_output(entry_lines[0], entry)
            else:
                for line in entry_lines:
                    if "=" not in line:
                        entry.add_parse_error(f"Invalid journal field format: {line}")
                        continue

                    try:
                        field_name, value = line.split("=", 1)

                        if not re.match(r"^[A-Z_][A-Z0-9_]*$", field_name):
                            entry.add_parse_error(
                                f"Invalid journal field name: {field_name}"
                            )
                            continue

                        if field_name in self.schema:
                            if field_name == "__REALTIME_TIMESTAMP":
                                entry.fields[field_name] = value
                                try:
                                    timestamp_float = float(value) / 1000000
                                    entry.timestamp = datetime.fromtimestamp(
                                        timestamp_float
                                    )
                                except (ValueError, OSError):
                                    entry.add_parse_error(
                                        f"Failed to parse realtime timestamp: {value}"
                                    )
                            else:
                                entry.fields[field_name] = self._convert_field_value(
                                    field_name, value
                                )

                    except ValueError as e:
                        entry.add_parse_error(
                            f"Error parsing field from line '{line}': {e}"
                        )
        except Exception as e:
            entry.add_parse_error(f"Systemd journal parsing error: {e}")

        return entry

    def parse_line(self, line, line_number=None) -> ParsedLogEntry:
        entry = ParsedLogEntry(fields={}, raw_line=line, line_number=line_number)

        try:
            if "=" in line:
                match = self.field_pattern.match(line)
                if not match:
                    entry.add_parse_error("Invalid journal field format")
                    return entry

                field_name, value = match.groups()

                if field_name in self.schema:
                    if field_name == "__REALTIME_TIMESTAMP":
                        entry.fields[field_name] = value
                        try:
                            timestamp_float = float(value) / 1000000
                            entry.timestamp = datetime.fromtimestamp(timestamp_float)
                        except (ValueError, OSError):
                            entry.add_parse_error(
                                f"Failed to parse realtime timestamp: {value}"
                            )
                    else:
                        entry.fields[field_name] = self._convert_field_value(
                            field_name, value
                        )
            else:
                self._parse_journalctl_output(line, entry)
        except Exception as e:
            entry.add_parse_error(f"Systemd journal parsing error: {e}")

        return entry

    def _parse_journalctl_output(self, line, entry):
        match = self.journalctl_pattern.match(line)
        if not match:
            entry.add_parse_error("Line does not match journalctl output format")
            if "message" in self.schema:
                entry.fields["message"] = line
            return

        timestamp_str, hostname, service, message = match.groups()
        field_mapping = {
            "timestamp": timestamp_str,
            "hostname": hostname,
            "service": service,
            "message": message,
        }

        for field_name, value in field_mapping.items():
            if field_name in self.schema:
                if field_name == "timestamp":
                    entry.fields[field_name] = value
                    try:
                        current_year = datetime.now().year
                        full_timestamp = f"{current_year} {timestamp_str}"
                        entry.timestamp = datetime.strptime(
                            full_timestamp, "%Y %b %d %H:%M:%S"
                        )
                    except ValueError:
                        self._map_field_value(entry, field_name, value)
                else:
                    entry.fields[field_name] = self._convert_field_value(
                        field_name, value
                    )
