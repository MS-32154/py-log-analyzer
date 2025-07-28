#!/usr/bin/env python3

"""
tui.py

Entry point for the Log Explorer TUI.

Author: MS-32154
email: msttoffg@gmail.com
Version: 0.1.0
License: MIT
Date: 2025-07-28
"""

import curses
import sys
from pathlib import Path
from datetime import datetime

from .inference.inference_engine import LogSchemaInferenceEngine
from .parser.parsing_engine import LogParsingEngine
from .search.search_engine import (
    LogSearchEngine,
    SearchQuery,
    SearchFilter,
    TimeFilter,
)
from .stats.analyzer import LogStatsAnalyzer


class BaseUI:
    """Base class with common UI utilities"""

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.init_colors()

    def init_colors(self):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        # Color pairs
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected
        curses.init_pair(2, curses.COLOR_RED, -1)  # Error
        curses.init_pair(3, curses.COLOR_GREEN, -1)  # Success
        curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Warning
        curses.init_pair(5, curses.COLOR_BLUE, -1)  # Info
        curses.init_pair(6, curses.COLOR_CYAN, -1)  # Highlight
        curses.init_pair(7, curses.COLOR_MAGENTA, -1)  # Plot

    def draw_centered_text(self, y, text, color=0):
        height, width = self.stdscr.getmaxyx()
        x = max(0, (width - len(text)) // 2)
        self.stdscr.addstr(y, x, text, color)

    def draw_truncated_text(self, y, x, text, max_width, color=0):
        if len(text) > max_width:
            text = text[: max_width - 3] + "..."
        self.stdscr.addstr(y, x, text, color)


class SearchForm:
    def __init__(self):
        self.fields = {
            "text_query": "",
            "field_name": "",
            "field_value": "",
            "operator": "contains",
            "case_sensitive": False,
            "start_time": "",
            "end_time": "",
            "last_hours": "",
            "last_minutes": "",
            "limit": "100",
            "offset": "0",
        }

        self.operators = ["contains", "equals", "regex", "gt", "gte", "lt", "lte"]
        self.current_field = 0
        self.field_order = [
            "text_query",
            "field_name",
            "field_value",
            "operator",
            "case_sensitive",
            "start_time",
            "end_time",
            "last_hours",
            "last_minutes",
            "limit",
            "offset",
        ]

        # Input state
        self.input_mode = False
        self.input_buffer = ""

        # Field type classification
        self.text_fields = {
            "text_query",
            "field_name",
            "field_value",
            "start_time",
            "end_time",
            "last_hours",
            "last_minutes",
            "limit",
            "offset",
        }
        self.toggle_fields = {"case_sensitive"}
        self.cycle_fields = {"operator"}

    def is_current_field_text(self):
        """Check if current field is a text input field"""
        field_key = self.field_order[self.current_field]
        return field_key in self.text_fields

    def enter_input_mode(self, initial_char=None):
        """Enter input mode for text fields"""
        if not self.is_current_field_text():
            return False

        field_key = self.field_order[self.current_field]
        self.input_mode = True

        if initial_char:
            self.input_buffer = initial_char
        else:
            # Start with current field value
            self.input_buffer = str(self.fields[field_key])

        return True

    def exit_input_mode(self, save=True):
        """Exit input mode, optionally saving the buffer"""
        if not self.input_mode:
            return

        if save:
            field_key = self.field_order[self.current_field]
            self.fields[field_key] = self.input_buffer

        self.input_mode = False
        self.input_buffer = ""

    def handle_input(self, key):
        """Handle all input with proper mode management"""
        if self.input_mode:
            return self._handle_input_mode(key)
        else:
            return self._handle_navigation_mode(key)

    def _handle_navigation_mode(self, key):
        """Handle navigation when not in input mode"""
        if key == curses.KEY_BTAB:  # Shift+Tab - navigate fields
            self.current_field = (self.current_field + 1) % len(self.field_order)
            return True

        elif key in (curses.KEY_UP, ord("k")):
            self.current_field = max(0, self.current_field - 1)
            return True

        elif key in (curses.KEY_DOWN, ord("j")):
            self.current_field = min(len(self.field_order) - 1, self.current_field + 1)
            return True

        elif key == ord(" "):  # Space - toggle/cycle non-text fields
            field_key = self.field_order[self.current_field]
            if field_key == "case_sensitive":
                self.fields[field_key] = not self.fields[field_key]
                return True
            elif field_key == "operator":
                current_idx = self.operators.index(self.fields[field_key])
                self.fields[field_key] = self.operators[
                    (current_idx + 1) % len(self.operators)
                ]
                return True
            # For text fields, space should not do anything in navigation mode
            return True

        elif key in (curses.KEY_BACKSPACE, 127, 8):  # Backspace - clear field
            field_key = self.field_order[self.current_field]
            if field_key == "case_sensitive":
                self.fields[field_key] = False
            elif field_key == "operator":
                self.fields[field_key] = "contains"
            else:
                self.fields[field_key] = ""
            return True

        elif key in (ord("\n"), ord("\r"), 10):  # Enter - start editing text field
            if self.is_current_field_text():
                self.enter_input_mode()
                return True
            # For non-text fields, return True to indicate we handled it
            return True

        elif 32 <= key <= 126:  # Printable chars - start editing with this character
            if self.is_current_field_text():
                self.enter_input_mode(chr(key))
                return True
            # For non-text fields, don't start input mode
            return True

        return False

    def _handle_input_mode(self, key):
        """Handle input when in text editing mode"""
        if key == 27:  # Escape - cancel input
            self.exit_input_mode(save=False)
            return True

        elif key in (ord("\n"), ord("\r"), 10):  # Enter - save and exit
            self.exit_input_mode(save=True)
            return True

        elif key in (curses.KEY_BACKSPACE, 127, 8):  # Backspace
            if self.input_buffer:
                self.input_buffer = self.input_buffer[:-1]
            return True

        elif key == 21:  # Ctrl+U - clear line
            self.input_buffer = ""
            return True

        elif 32 <= key <= 126:  # Printable characters
            self.input_buffer += chr(key)
            return True

        return False

    def draw(self, stdscr, start_y, width, detection_result=None):
        y = start_y

        stdscr.addstr(y, 1, "Search Query Builder:", curses.A_BOLD)
        y += 2

        # Available fields
        if detection_result and detection_result.schema:
            field_names = list(detection_result.schema.keys())
            fields_text = "Available Fields: " + ", ".join(field_names[:8])
            if len(fields_text) > width - 5:
                fields_text = fields_text[: width - 8] + "..."
            stdscr.addstr(y, 1, fields_text, curses.color_pair(5))
            y += 2

        # Time format help
        stdscr.addstr(
            y,
            1,
            "Time Format: YYYY-MM-DD HH:MM:SS (e.g., 2024-01-15 14:30:00)",
            curses.color_pair(4),
        )
        y += 2

        # Form fields
        for i, field_key in enumerate(self.field_order):
            if y >= start_y + 20:
                break

            # Field selection indicator
            if i == self.current_field:
                if self.input_mode:
                    stdscr.addstr(y, 1, ">>> ", curses.color_pair(6) | curses.A_BOLD)
                else:
                    stdscr.addstr(y, 1, "->  ", curses.color_pair(1) | curses.A_BOLD)
                label_color = curses.color_pair(1) | curses.A_BOLD
            else:
                stdscr.addstr(y, 1, "    ")
                label_color = 0

            # Field label
            label = self._get_field_label(field_key)
            label_formatted = f"{label}:".ljust(16)
            stdscr.addstr(y, 5, label_formatted, label_color)

            # Field value
            if self.input_mode and i == self.current_field:
                value = self.input_buffer + "_"  # Show cursor
                stdscr.addstr(y, 22, value, curses.color_pair(6))
            else:
                value = self._get_field_display_value(field_key)
                max_value_width = width - 25
                if len(value) > max_value_width:
                    value = value[: max_value_width - 3] + "..."

                color = self._get_field_color(field_key)
                stdscr.addstr(y, 22, value, color)

            y += 1

        y += 1

        # Instructions based on current mode
        if self.input_mode:
            instructions = [
                "INPUT MODE: Type to edit | Enter: save | Esc: cancel | Ctrl+U: clear line"
            ]
        else:
            instructions = [
                "NAVIGATION: Shift+Tab/Up/Down: move | Enter/Type: edit text | Space: toggle",
                "Enter: execute search | Search results: v=toggle view, PgUp/PgDn=scroll",
            ]

        for instruction in instructions:
            if y < start_y + 22:
                stdscr.addstr(y, 1, instruction[: width - 2], curses.color_pair(4))
                y += 1

        return y

    def _get_field_label(self, field_key):
        labels = {
            "text_query": "Text Search",
            "field_name": "Field Name",
            "field_value": "Field Value",
            "operator": "Operator",
            "case_sensitive": "Case Sensitive",
            "start_time": "Start Time",
            "end_time": "End Time",
            "last_hours": "Last Hours",
            "last_minutes": "Last Minutes",
            "limit": "Limit",
            "offset": "Offset",
        }
        return labels.get(field_key, field_key)

    def _get_field_display_value(self, field_key):
        value = self.fields[field_key]

        if field_key == "case_sensitive":
            return "Yes" if value else "No"
        elif field_key == "operator":
            return f"{value}"
        elif not value:
            return "<empty>"
        else:
            return str(value)

    def _get_field_color(self, field_key):
        if field_key in self.text_fields:
            return (
                curses.color_pair(3) if self.fields[field_key] else curses.color_pair(4)
            )
        else:
            return curses.color_pair(3)

    def build_query(self):
        query = SearchQuery()

        # Text search
        if self.fields["text_query"].strip():
            query.text = self.fields["text_query"].strip()

        # Field filters
        filters = []
        if self.fields["field_name"].strip() and self.fields["field_value"].strip():
            search_filter = SearchFilter(
                field_name=self.fields["field_name"].strip(),
                value=self.fields["field_value"].strip(),
                operator=self.fields["operator"],
                case_sensitive=self.fields["case_sensitive"],
            )
            filters.append(search_filter)

        query.filters = filters

        # Time filter
        time_filter = None
        if self.fields["start_time"].strip() or self.fields["end_time"].strip():
            time_filter = TimeFilter()

            if self.fields["start_time"].strip():
                time_filter.start_time = datetime.strptime(
                    self.fields["start_time"].strip(), "%Y-%m-%d %H:%M:%S"
                )

            if self.fields["end_time"].strip():
                time_filter.end_time = datetime.strptime(
                    self.fields["end_time"].strip(), "%Y-%m-%d %H:%M:%S"
                )

        elif self.fields["last_hours"].strip():
            hours = int(self.fields["last_hours"].strip())
            time_filter = TimeFilter(last_hours=hours)

        elif self.fields["last_minutes"].strip():
            minutes = int(self.fields["last_minutes"].strip())
            time_filter = TimeFilter(last_minutes=minutes)

        query.time_filter = time_filter

        # Pagination
        if self.fields["limit"].strip():
            query.limit = int(self.fields["limit"].strip())
        if self.fields["offset"].strip():
            query.offset = int(self.fields["offset"].strip())

        return query


class ScrollableContent:
    """Mixin for scrollable content management"""

    def __init__(self):
        self.scroll_positions = {"main": 0, "results": 0, "field_values": 0, "files": 0}

    def scroll(self, content_type, delta, max_items=None):
        current = self.scroll_positions.get(content_type, 0)
        new_pos = current + delta

        if max_items is not None:
            new_pos = max(0, min(new_pos, max_items - 1))
        else:
            new_pos = max(0, new_pos)

        self.scroll_positions[content_type] = new_pos
        return new_pos


class LogExplorerTUI(BaseUI, ScrollableContent):
    def __init__(self, stdscr):
        BaseUI.__init__(self, stdscr)
        ScrollableContent.__init__(self)

        self.current_tab = 0
        self.tabs = ["Files", "Search", "Stats", "Plots", "Help"]

        # Initialize engines
        self.inference_engine = LogSchemaInferenceEngine()
        self.parsing_engine = LogParsingEngine()
        self.search_engine = LogSearchEngine()
        self.stats_analyzer = LogStatsAnalyzer()

        # Analysis data
        self.current_file = None
        self.detection_result = None
        self.parse_result = None
        self.insights = None

        # Search state
        self.search_results = None
        self.search_form = SearchForm()
        self.show_raw_lines = False

        # UI state
        self.status_message = ""
        self.error_message = ""

        # File browser state
        self.current_dir = Path.cwd()
        self.dir_contents = []

        self.refresh_dir_contents()

    def refresh_dir_contents(self):
        try:
            self.dir_contents = []
            if self.current_dir.parent != self.current_dir:
                self.dir_contents.append(("..", True))

            for item in sorted(self.current_dir.iterdir()):
                if item.is_dir():
                    self.dir_contents.append((item.name, True))
                elif item.suffix.lower() in [
                    ".log",
                    ".txt",
                    ".csv",
                    ".json",
                    ".gz",
                    ".bz2",
                    ".xz",
                    ".lzma",
                ]:
                    self.dir_contents.append((item.name, False))
        except PermissionError:
            self.error_message = f"Permission denied: {self.current_dir}"

    def run(self):
        while True:
            try:
                self.draw()
                key = self.stdscr.getch()
                if not self.handle_input(key):
                    break
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.error_message = f"Error: {str(e)}"

    def draw(self):
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        # Draw header
        self.draw_header(width)

        # Draw tabs
        self.draw_tabs(width)

        # Draw main content
        content_start = 4
        content_height = height - content_start - 2

        # Tab content dispatch
        tab_handlers = {
            0: self.draw_files_tab,
            1: self.draw_search_tab,
            2: self.draw_stats_tab,
            3: self.draw_plots_tab,
            4: self.draw_help_tab,
        }

        handler = tab_handlers.get(self.current_tab)
        if handler:
            handler(content_start, content_height, width)

        # Draw status bar
        self.draw_status_bar(height - 1, width)
        self.stdscr.refresh()

    def draw_header(self, width):
        title = "Log Explorer TUI - Single File Analysis"
        self.draw_centered_text(0, title, curses.A_BOLD)

        # Current file info
        if self.current_file:
            file_info = f"File: {self.current_file}"
            self.draw_truncated_text(1, 1, file_info, width - 2, curses.color_pair(5))

    def draw_tabs(self, width):
        y = 2
        x = 1
        for i, tab in enumerate(self.tabs):
            if i == self.current_tab:
                self.stdscr.addstr(y, x, f"[{tab}]", curses.color_pair(1))
            else:
                self.stdscr.addstr(y, x, f" {tab} ")
            x += len(tab) + 4

    def draw_files_tab(self, start_y, height, width):
        y = start_y

        # Current directory
        self.stdscr.addstr(y, 1, f"Directory: {self.current_dir}", curses.A_BOLD)
        y += 2

        # Directory contents
        self.stdscr.addstr(y, 1, "Directory Contents:", curses.A_UNDERLINE)
        y += 1

        scroll_pos = self.scroll_positions["files"]
        for i, (name, is_dir) in enumerate(self.dir_contents[scroll_pos:]):
            if y >= start_y + height - 8:
                break

            prefix = "[DIR] " if is_dir else "[FILE] "
            display_name = name
            max_name_width = width - len(prefix) - 5

            if len(display_name) > max_name_width:
                display_name = display_name[: max_name_width - 3] + "..."

            # Highlight current selection
            if i + scroll_pos == scroll_pos:
                color = curses.color_pair(1)
            else:
                color = curses.color_pair(6) if is_dir else 0

            self.stdscr.addstr(y, 3, prefix + display_name, color)
            y += 1

        # Current file status
        if self.current_file:
            y += 1
            self.stdscr.addstr(
                y,
                1,
                f"Current File: {Path(self.current_file).name}",
                curses.A_UNDERLINE,
            )
            y += 1

            status_items = []
            if self.detection_result:
                status_items.extend(
                    [
                        f"Format: {self.detection_result.format_type.value}",
                        f"Confidence: {self.detection_result.confidence:.3f}",
                    ]
                )
            if self.parse_result:
                status_items.extend(
                    [
                        f"Lines: {self.parse_result.total_lines}",
                        f"Success: {self.parse_result.success_rate:.1%}",
                    ]
                )
            if self.insights:
                status_items.append(f"Quality: {self.insights.quality_score:.2f}")

            for item in status_items:
                if y >= start_y + height - 4:
                    break
                self.stdscr.addstr(y, 3, item, curses.color_pair(3))
                y += 1

        # Instructions
        instructions = [
            "Navigation: Up/Down (navigate), Enter (select/load), 'c' (change dir)",
            "File ops: 'r' (refresh), 'p' (process file), Tab (next tab), 'q' (quit)",
        ]

        y = start_y + height - len(instructions) - 1
        for instruction in instructions:
            if y < start_y + height:
                self.stdscr.addstr(y, 1, instruction, curses.color_pair(4))
                y += 1

    def draw_search_tab(self, start_y, height, width):
        y = start_y

        if not self.current_file or not self.parse_result:
            self.stdscr.addstr(
                y,
                1,
                "No file loaded. Go to Files tab and load a file.",
                curses.color_pair(2),
            )
            return

        # Search form
        form_height = self.search_form.draw(
            self.stdscr, y, width, self.detection_result
        )
        y = form_height + 1

        # Only show toggle and results if not in input mode
        if not self.search_form.input_mode:
            # Toggle raw lines view
            toggle_text = f"View: {'Raw Lines' if self.show_raw_lines else 'Parsed Fields'} (press 'v' to toggle)"
            self.stdscr.addstr(y, 1, toggle_text, curses.color_pair(6))
            y += 2

        # Search results
        if self.search_results:
            self._draw_search_results(y, start_y, height, width)

    def _draw_search_results(self, y, start_y, height, width):
        """Draw search results section"""
        results_count = len(self.search_results.entries)
        total_matches = self.search_results.total_matches
        search_time = self.search_results.search_time

        self.stdscr.addstr(
            y,
            1,
            f"Results: {results_count} shown, {total_matches} total, {search_time:.3f}s",
            curses.A_BOLD,
        )
        y += 1

        # Field counts summary (only if not showing raw lines)
        if self.search_results.field_counts and not self.show_raw_lines:
            y = self._draw_field_counts_table(y, start_y, height, width)

        # Search Results
        y = self._draw_results_table(y, start_y, height, width)

    def _draw_field_counts_table(self, y, start_y, height, width):
        """Draw field counts summary table"""
        self.stdscr.addstr(y, 1, "Top Field Values:", curses.A_UNDERLINE)
        y += 1

        # Table header
        self.stdscr.addstr(
            y, 1, "Field Name".ljust(20) + "Value".ljust(25) + "Count", curses.A_BOLD
        )
        y += 1
        self.stdscr.addstr(y, 1, "-" * 50, curses.color_pair(5))
        y += 1

        # Prepare field value pairs
        field_value_pairs = []
        for field_name, value_counts in self.search_results.field_counts.items():
            for value, count in list(value_counts.items())[:3]:  # Top 3 per field
                field_value_pairs.append((field_name, str(value), count))

        # Display with scrolling
        scroll_pos = self.scroll_positions["field_values"]
        display_count = min(5, len(field_value_pairs) - scroll_pos)

        for i in range(display_count):
            if y >= start_y + height - 12:
                break
            idx = scroll_pos + i
            field_name, value, count = field_value_pairs[idx]

            # Truncate long values
            field_display = field_name[:19].ljust(20)
            value_display = value[:24].ljust(25)
            count_display = str(count)

            self.stdscr.addstr(y, 1, field_display, curses.color_pair(5))
            self.stdscr.addstr(y, 21, value_display)
            self.stdscr.addstr(y, 46, count_display, curses.color_pair(3))
            y += 1

        if len(field_value_pairs) > 5:
            nav_text = f"Showing {scroll_pos+1}-{scroll_pos+display_count} of {len(field_value_pairs)} (F/B: scroll field values)"
            self.stdscr.addstr(y, 1, nav_text, curses.color_pair(4))
            y += 1
        y += 1

        return y

    def _draw_results_table(self, y, start_y, height, width):
        """Draw the main results table"""
        self.stdscr.addstr(y, 1, "Search Results:", curses.A_UNDERLINE)
        y += 1

        scroll_pos = self.scroll_positions["results"]

        if self.show_raw_lines:
            y = self._draw_raw_lines_table(y, start_y, height, width, scroll_pos)
        else:
            y = self._draw_parsed_fields_table(y, start_y, height, width, scroll_pos)

        # Navigation info
        if len(self.search_results.entries) > 10:
            total_entries = len(self.search_results.entries)
            display_start = scroll_pos + 1
            display_end = min(scroll_pos + 10, total_entries)
            nav_text = f"Results: {display_start}-{display_end} of {total_entries} (PgUp/PgDn: scroll results)"
            self.stdscr.addstr(y, 1, nav_text, curses.color_pair(4))
            y += 1

        return y

    def _draw_raw_lines_table(self, y, start_y, height, width, scroll_pos):
        """Draw raw lines table"""
        # Header
        self.stdscr.addstr(y, 1, "#".ljust(6) + "Raw Line", curses.A_BOLD)
        y += 1
        self.stdscr.addstr(y, 1, "-" * (width - 2), curses.color_pair(5))
        y += 1

        # Lines
        for i, entry in enumerate(self.search_results.entries[scroll_pos:]):
            if y >= start_y + height - 4:
                break

            raw_line = getattr(entry, "raw_line", str(entry))
            line_num = str(i + scroll_pos + 1).ljust(6)

            # Truncate long lines
            max_line_length = width - 8
            if len(raw_line) > max_line_length:
                raw_line = raw_line[: max_line_length - 3] + "..."

            self.stdscr.addstr(y, 1, line_num, curses.color_pair(6))
            self.stdscr.addstr(y, 7, raw_line)
            y += 1

        return y

    def _draw_parsed_fields_table(self, y, start_y, height, width, scroll_pos):
        """Draw parsed fields table"""
        # Get field names for headers
        all_field_names = set()
        for entry in self.search_results.entries:
            if hasattr(entry, "fields") and entry.fields:
                all_field_names.update(entry.fields.keys())

        field_names = sorted(list(all_field_names))
        max_fields = min(len(field_names), (width - 20) // 15)
        display_fields = field_names[:max_fields]

        # Column widths
        col_widths = {"#": 4, "Time": 12}
        remaining_width = width - col_widths["#"] - col_widths["Time"] - 2
        if display_fields:
            field_width = max(8, remaining_width // len(display_fields))
            for field in display_fields:
                col_widths[field] = min(field_width, 20)

        # Header
        header_line = "#".ljust(col_widths["#"]) + "Time".ljust(col_widths["Time"])
        for field in display_fields:
            header_line += field[: col_widths[field] - 1].ljust(col_widths[field])

        self.stdscr.addstr(y, 1, header_line[: width - 2], curses.A_BOLD)
        y += 1
        self.stdscr.addstr(
            y, 1, "-" * min(len(header_line), width - 2), curses.color_pair(5)
        )
        y += 1

        # Entries
        for i, entry in enumerate(self.search_results.entries[scroll_pos:]):
            if y >= start_y + height - 4:
                break

            # Build line content
            entry_num = str(i + scroll_pos + 1).ljust(col_widths["#"])
            line_content = entry_num

            # Timestamp
            if hasattr(entry, "timestamp") and entry.timestamp:
                time_str = entry.timestamp.strftime("%m-%d %H:%M")[
                    : col_widths["Time"] - 1
                ].ljust(col_widths["Time"])
            else:
                time_str = "No Time".ljust(col_widths["Time"])
            line_content += time_str

            # Fields
            if hasattr(entry, "fields") and entry.fields:
                for field_name in display_fields:
                    field_value = entry.fields.get(field_name, "")
                    if field_value is not None:
                        field_str = str(field_value)[
                            : col_widths[field_name] - 1
                        ].ljust(col_widths[field_name])
                    else:
                        field_str = "-".ljust(col_widths[field_name])
                    line_content += field_str
            else:
                # Fill empty columns
                for field_name in display_fields:
                    line_content += "-".ljust(col_widths[field_name])

            # Display the line
            self.stdscr.addstr(y, 1, line_content[: width - 2])
            y += 1

        # Show field truncation info
        if len(field_names) > max_fields:
            truncated_msg = f"Showing {len(display_fields)}/{len(field_names)} fields. Hidden: {', '.join(field_names[max_fields:max_fields+3])}{'...' if len(field_names) > max_fields + 3 else ''}"
            self.stdscr.addstr(y, 1, truncated_msg[: width - 2], curses.color_pair(4))
            y += 1

        return y

    def draw_stats_tab(self, start_y, height, width):
        y = start_y

        if not self.insights:
            self.stdscr.addstr(
                y, 1, "No analysis data. Process file first.", curses.color_pair(2)
            )
            return

        scroll_pos = self.scroll_positions["main"]
        content_lines = self._get_stats_content_lines()

        # Display content with scrolling
        for line_data in content_lines[scroll_pos:]:
            if y >= start_y + height - 2:
                break

            text, color, indent = line_data
            self.stdscr.addstr(y, 1 + indent, text[: width - 2 - indent], color)
            y += 1

    def _get_stats_content_lines(self):
        """Generate all stats content lines for scrolling"""
        lines = []

        # Format Detection Stats
        lines.append(
            ("═══ FORMAT DETECTION ═══", curses.A_BOLD | curses.color_pair(6), 0)
        )

        format_stats = self.insights.format_stats
        format_info = [
            f"Format Type: {format_stats.format_type}",
            f"Detection Confidence: {format_stats.detection_confidence:.3f}",
            f"Schema Size: {format_stats.schema_size} fields",
            f"Timestamp Fields: {format_stats.timestamp_fields}",
            f"High Confidence Fields: {format_stats.high_confidence_fields}",
            f"Low Confidence Fields: {format_stats.low_confidence_fields}",
            f"Sample Line Count: {format_stats.sample_line_count}",
        ]

        for info in format_info:
            color = (
                curses.color_pair(3)
                if "Confidence" in info and format_stats.detection_confidence > 0.8
                else 0
            )
            lines.append((info, color, 1))

        lines.append(("", 0, 0))  # Empty line

        # Parsing Performance Stats
        lines.append(
            ("═══ PARSING PERFORMANCE ═══", curses.A_BOLD | curses.color_pair(6), 0)
        )

        parsing_stats = self.insights.parsing_stats
        parsing_info = [
            f"Total Lines: {parsing_stats.total_lines:,}",
            f"Successfully Parsed: {parsing_stats.successfully_parsed:,}",
            f"Malformed Lines: {parsing_stats.malformed_lines:,}",
            f"Success Rate: {parsing_stats.success_rate:.1%}",
            f"Average Confidence: {parsing_stats.average_confidence:.3f}",
        ]

        for info in parsing_info:
            color = (
                curses.color_pair(3)
                if parsing_stats.success_rate > 0.8 and "Success Rate" in info
                else 0
            )
            lines.append((info, color, 1))

        # Error Distribution
        if parsing_stats.error_distribution:
            lines.append(("", 0, 0))
            lines.append(("Error Types:", curses.A_UNDERLINE, 1))
            for error_type, count in parsing_stats.error_distribution.items():
                lines.append((f"{error_type}: {count:,}", curses.color_pair(2), 2))

        # Field Extraction Rates
        if parsing_stats.field_extraction_rates:
            lines.append(("", 0, 0))
            lines.append(("Field Extraction Rates:", curses.A_UNDERLINE, 1))
            for field_name, rate in parsing_stats.field_extraction_rates.items():
                color = (
                    curses.color_pair(3)
                    if rate > 0.8
                    else curses.color_pair(4) if rate < 0.5 else 0
                )
                lines.append((f"{field_name}: {rate:.1%}", color, 2))

        lines.append(("", 0, 0))

        # Field Statistics
        lines.append(
            ("═══ FIELD STATISTICS ═══", curses.A_BOLD | curses.color_pair(6), 0)
        )

        for field in self.insights.field_stats:
            # Field header
            field_header = f"Field: {field.name} ({field.data_type})"
            if field.is_timestamp:
                field_header += " [TIMESTAMP]"
            lines.append((field_header, curses.A_BOLD, 1))

            # Field metrics
            metrics = [
                f"Extraction Rate: {field.extraction_rate:.1%} ({field.total_extracted:,} entries)",
                f"Unique Values: {field.unique_values:,}",
                f"Null Rate: {field.null_rate:.1%}",
                f"Confidence: {field.confidence:.3f}",
            ]

            for metric in metrics:
                color = (
                    curses.color_pair(3)
                    if field.extraction_rate > 0.8
                    else curses.color_pair(4) if field.extraction_rate < 0.5 else 0
                )
                lines.append((metric, color, 2))

            # Most common values
            if field.most_common_values:
                common_values = ", ".join(
                    [f"{v}({c})" for v, c in field.most_common_values[:5]]
                )
                lines.append((f"Top Values: {common_values}", curses.color_pair(5), 2))
            lines.append(("", 0, 0))

        # Time Series Stats
        if self.insights.time_series_stats:
            lines.append(
                (
                    "═══ TIME SERIES ANALYSIS ═══",
                    curses.A_BOLD | curses.color_pair(6),
                    0,
                )
            )

            ts_stats = self.insights.time_series_stats
            ts_info = [
                f"Total Timestamps: {len(ts_stats.timestamps):,}",
                f"Time Range: {ts_stats.time_range}",
                f"Peak Hour: {ts_stats.peak_hour}:00",
                f"Peak Day: {ts_stats.peak_day}",
                f"Entries per Second: {ts_stats.entries_per_second:.3f}",
                f"Hour Distribution: {len(ts_stats.counts_per_hour)} unique hours",
                f"Day Distribution: {len(ts_stats.counts_per_day)} unique days",
            ]

            for info in ts_info:
                lines.append((info, 0, 1))

        return lines

    def draw_plots_tab(self, start_y, height, width):
        y = start_y

        if not self.insights:
            self.stdscr.addstr(
                y, 1, "No analysis data. Process file first.", curses.color_pair(2)
            )
            return

        # Field Extraction Rates Bar Chart
        if self.insights.parsing_stats.field_extraction_rates:
            self.stdscr.addstr(
                y, 1, "Field Extraction Rates", curses.A_BOLD | curses.color_pair(6)
            )
            y += 1

            rates = list(self.insights.parsing_stats.field_extraction_rates.items())[:8]
            if rates:
                max_rate = max(rate for _, rate in rates)
                for field_name, rate in rates:
                    if y >= start_y + height - 25:
                        break

                    bar_length = int((rate / max_rate) * 30) if max_rate > 0 else 0
                    bar = "█" * bar_length + "░" * (30 - bar_length)

                    field_display = field_name[:15].ljust(15)
                    color = (
                        curses.color_pair(3)
                        if rate > 0.8
                        else curses.color_pair(4) if rate < 0.5 else 0
                    )
                    self.stdscr.addstr(
                        y, 2, f"{field_display} |{bar}| {rate:.1%}", color
                    )
                    y += 1
            y += 2

        # Hourly Distribution Plot
        if (
            self.insights.time_series_stats
            and self.insights.time_series_stats.counts_per_hour
        ):
            self.stdscr.addstr(
                y, 1, "Hourly Distribution", curses.A_BOLD | curses.color_pair(6)
            )
            y += 1

            hour_counts = self.insights.time_series_stats.counts_per_hour
            if hour_counts:
                max_count = max(hour_counts.values())

                for hour in range(24):
                    if y >= start_y + height - 15:
                        break

                    count = hour_counts.get(hour, 0)
                    if count > 0:
                        bar_length = (
                            int((count / max_count) * 25) if max_count > 0 else 0
                        )
                        bar = "█" * bar_length
                        self.stdscr.addstr(
                            y,
                            2,
                            f"{hour:02d}:00 |{bar.ljust(25)}| {count:,}",
                            curses.color_pair(7),
                        )
                        y += 1
            y += 2

        # Quality Metrics Gauge
        quality_score = self.insights.quality_score
        self.stdscr.addstr(
            y, 1, "Quality Score Breakdown", curses.A_BOLD | curses.color_pair(6)
        )
        y += 1

        # Overall quality gauge
        gauge_length = 30
        filled_length = int(quality_score * gauge_length)
        gauge = "█" * filled_length + "░" * (gauge_length - filled_length)

        color = (
            curses.color_pair(3)
            if quality_score > 0.8
            else curses.color_pair(4) if quality_score < 0.5 else curses.color_pair(5)
        )
        self.stdscr.addstr(
            y, 2, f"Overall".ljust(15) + f" |{gauge}| {quality_score:.3f}", color
        )
        y += 1

        # Component scores
        if hasattr(self.insights, "format_stats") and hasattr(
            self.insights, "parsing_stats"
        ):
            detection_score = self.insights.format_stats.detection_confidence
            parsing_score = self.insights.parsing_stats.success_rate

            for label, score in [
                ("Detection", detection_score),
                ("Parsing", parsing_score),
            ]:
                if y >= start_y + height - 3:
                    break
                filled = int(score * 30)
                gauge = "█" * filled + "░" * (30 - filled)
                color = (
                    curses.color_pair(3)
                    if score > 0.8
                    else curses.color_pair(4) if score < 0.5 else 0
                )
                self.stdscr.addstr(
                    y, 2, f"{label.ljust(15)} |{gauge}| {score:.3f}", color
                )
                y += 1

    def draw_help_tab(self, start_y, height, width):
        help_text = [
            "LOG EXPLORER TUI - SINGLE FILE ANALYSIS",
            "",
            "WORKFLOW:",
            "  1. FILES TAB: Navigate and load a log file",
            "  2. Process with 'p' to analyze the file",
            "  3. SEARCH TAB: Query and filter log entries",
            "  4. STATS TAB: View complete analysis metrics",
            "  5. PLOTS TAB: Visual representations of data",
            "",
            "GLOBAL CONTROLS:",
            "  Tab              - Switch to next tab",
            "  q                - Quit application",
            "  Page Up/Down     - Scroll content",
            "",
            "FILES TAB:",
            "  Up/Down          - Navigate directory",
            "  Enter            - Enter directory or load file",
            "  c                - Change directory (input mode)",
            "  r                - Refresh directory listing",
            "  p                - Process current file (full analysis)",
            "",
            "SEARCH TAB:",
            "  NAVIGATION MODE:",
            "    Shift+Tab      - Move between form fields",
            "    Up/Down        - Move between form fields",
            "    Enter/Type     - Start editing text fields",
            "    Space          - Toggle boolean/cycle operator",
            "    Backspace      - Clear current field",
            "    Enter          - Execute search (when not editing and no text field highlighted)",
            "                    !Highlight Operator/Case Sensitive!",
            "  INPUT MODE:",
            "    Type           - Edit text",
            "    Enter          - Save and exit input mode",
            "    Esc            - Cancel and exit input mode",
            "    Ctrl+U         - Clear current line",
            "  RESULTS:",
            "    v              - Toggle raw lines view",
            "    Page Up/Down   - Scroll search results",
            "    F/B            - Scroll field values table",
            "",
            "TIME FORMAT:",
            "  Use: YYYY-MM-DD HH:MM:SS",
            "  Example: 2024-01-15 14:30:00",
            "",
            "SUPPORTED FORMATS:",
            "  JSON, CSV, LTSV, Key-Value pairs",
            "  Apache/Nginx access & error logs",
            "  Syslog, Systemd Journal entries",
            "  Python logging, Basic log formats",
            "",
            "COMPRESSION SUPPORT:",
            "  .gz (gzip), .bz2 (bzip2), .xz (xz), .lzma (lzma)",
        ]

        scroll_pos = self.scroll_positions["main"]
        y = start_y
        for line in help_text[scroll_pos:]:
            if y >= start_y + height - 1:
                break

            if line.startswith("LOG EXPLORER"):
                color = curses.A_BOLD | curses.color_pair(6)
            elif line.endswith(":") and not line.startswith("  "):
                color = curses.A_UNDERLINE | curses.color_pair(5)
            elif line.startswith("  ") and " - " in line:
                parts = line.split(" - ", 1)
                self.stdscr.addstr(y, 1, parts[0], curses.color_pair(6))
                if len(parts) > 1:
                    self.stdscr.addstr(y, len(parts[0]) + 3, parts[1])
                y += 1
                continue
            else:
                color = 0

            self.stdscr.addstr(y, 1, line, color)
            y += 1

    def draw_status_bar(self, y, width):
        # Clear the line
        self.stdscr.addstr(y, 0, " " * (width - 1))

        # Status message
        if self.error_message:
            msg = f"ERROR: {self.error_message}"
            self.stdscr.addstr(y, 1, msg[: width - 2], curses.color_pair(2))
            self.error_message = ""  # Clear after showing
        elif self.status_message:
            self.stdscr.addstr(
                y, 1, self.status_message[: width - 2], curses.color_pair(3)
            )
        else:
            # Default status
            tab_name = self.tabs[self.current_tab]
            file_status = (
                f"File: {Path(self.current_file).name}"
                if self.current_file
                else "No file"
            )
            mode_status = (
                " [INPUT MODE]"
                if (self.current_tab == 1 and self.search_form.input_mode)
                else ""
            )
            default_msg = f"{tab_name}{mode_status} | {file_status} | Press 'q' to quit"
            self.stdscr.addstr(y, 1, default_msg[: width - 2])

    def handle_input(self, key):
        # Global keys (always processed first)
        if key == ord("q"):
            return False
        elif key == 27:  # ESC key - handle properly without exiting
            if self.current_tab == 1 and self.search_form.input_mode:
                # Let search form handle ESC to exit input mode
                self.search_form.handle_input(key)
            # For other cases, just ignore ESC (don't exit the application)
            return True
        elif key == ord("\t") or key == 9:  # Tab
            if self.current_tab == 1:  # Search tab special handling
                if not self.search_form.input_mode:
                    self.current_tab = (self.current_tab + 1) % len(self.tabs)
                    self._reset_scroll_positions()
                # If in input mode, let search form handle it
            else:
                self.current_tab = (self.current_tab + 1) % len(self.tabs)
                self._reset_scroll_positions()
        elif key == curses.KEY_BTAB:  # Shift+Tab
            if self.current_tab == 1:  # Search tab - pass to form
                handled = self.search_form.handle_input(key)
                return handled
            else:
                self.current_tab = (self.current_tab - 1) % len(self.tabs)
                self._reset_scroll_positions()
        elif key == curses.KEY_PPAGE:  # Page Up
            self._handle_scroll(key)
        elif key == curses.KEY_NPAGE:  # Page Down
            self._handle_scroll(key)
        else:
            # Tab-specific input handling
            return self._handle_tab_specific_input(key)

        return True

    def _reset_scroll_positions(self):
        """Reset scroll positions when changing tabs"""
        for key in self.scroll_positions:
            self.scroll_positions[key] = 0

    def _handle_scroll(self, key):
        """Handle scrolling for different tabs and contexts"""
        if self.current_tab == 1:  # Search tab
            if key == curses.KEY_PPAGE:  # Page Up
                self.scroll(
                    "results",
                    -10,
                    len(self.search_results.entries) if self.search_results else 0,
                )
            elif key == curses.KEY_NPAGE:  # Page Down
                self.scroll(
                    "results",
                    10,
                    len(self.search_results.entries) if self.search_results else 0,
                )
        else:  # Other tabs
            if key == curses.KEY_PPAGE:
                self.scroll("main", -10)
            elif key == curses.KEY_NPAGE:
                self.scroll("main", 10)

    def _handle_tab_specific_input(self, key):
        """Route input to appropriate tab handler"""
        if self.current_tab == 0:  # Files
            return self._handle_files_input(key)
        elif self.current_tab == 1:  # Search
            return self._handle_search_input(key)
        elif self.current_tab in [2, 3, 4]:  # Stats/Plots/Help
            return self._handle_scroll_only_input(key)
        return True

    def _handle_files_input(self, key):
        """Handle files tab input"""
        if key == curses.KEY_UP:
            self.scroll("files", -1, len(self.dir_contents))
        elif key == curses.KEY_DOWN:
            self.scroll("files", 1, len(self.dir_contents))
        elif key in (ord("\n"), ord("\r"), 10):  # Enter
            self._select_file_or_directory()
        elif key == ord("c"):  # Change directory
            self._prompt_change_directory()
        elif key == ord("r"):  # Refresh
            self.refresh_dir_contents()
            self.status_message = "Directory refreshed"
        elif key == ord("p"):  # Process file
            self._process_current_file()
        return True

    def _handle_search_input(self, key):
        """Handle search tab input with proper mode awareness"""
        # If in input mode, let form handle ALL input
        if self.search_form.input_mode:
            handled = self.search_form.handle_input(key)
            return handled

        # Navigation mode - handle search-specific keys first
        if key == ord("v"):  # Toggle view (only in navigation mode)
            self.show_raw_lines = not self.show_raw_lines
            return True
        elif key in (ord("f"), ord("F")):  # Scroll field values forward
            if self.search_results and self.search_results.field_counts:
                total_pairs = sum(
                    min(3, len(counts))
                    for counts in self.search_results.field_counts.values()
                )
                self.scroll("field_values", 1, total_pairs)
            return True
        elif key in (ord("b"), ord("B")):  # Scroll field values backward
            self.scroll("field_values", -1)
            return True
        elif key in (ord("\n"), ord("\r"), 10):  # Enter - execute search
            # Only execute search if not on a text field or if we're not starting input mode
            field_key = self.search_form.field_order[self.search_form.current_field]
            if field_key not in self.search_form.text_fields:
                self._execute_search()
                return True
            else:
                # Let the form handle Enter for text fields
                handled = self.search_form.handle_input(key)
                return handled
        else:
            # Let form handle other navigation and input
            handled = self.search_form.handle_input(key)
            return handled

    def _handle_scroll_only_input(self, key):
        """Handle input for tabs that only support scrolling"""
        if key == curses.KEY_UP:
            self.scroll("main", -1)
        elif key == curses.KEY_DOWN:
            self.scroll("main", 1)
        return True

    def _select_file_or_directory(self):
        """Select file or navigate directory"""
        file_pos = self.scroll_positions["files"]
        if not self.dir_contents or file_pos >= len(self.dir_contents):
            return

        name, is_dir = self.dir_contents[file_pos]

        if name == "..":
            self.current_dir = self.current_dir.parent
            self.refresh_dir_contents()
            self.scroll_positions["files"] = 0
        elif is_dir:
            new_dir = self.current_dir / name
            if new_dir.exists() and new_dir.is_dir():
                self.current_dir = new_dir
                self.refresh_dir_contents()
                self.scroll_positions["files"] = 0
        else:
            # Load file
            filepath = self.current_dir / name
            self.current_file = str(filepath)
            self.status_message = f"Loaded file: {name}"
            # Clear previous analysis data
            self.detection_result = None
            self.parse_result = None
            self.insights = None
            self.search_results = None

    def _prompt_change_directory(self):
        """Prompt for directory change"""
        curses.echo()
        curses.curs_set(1)

        height, width = self.stdscr.getmaxyx()
        prompt = "Enter directory path: "
        self.stdscr.addstr(height - 2, 1, prompt)
        self.stdscr.refresh()

        try:
            input_str = self.stdscr.getstr(
                height - 2, len(prompt) + 1, width - len(prompt) - 3
            ).decode("utf-8")
            if input_str.strip():
                new_dir = Path(input_str.strip()).expanduser().resolve()
                if new_dir.exists() and new_dir.is_dir():
                    self.current_dir = new_dir
                    self.refresh_dir_contents()
                    self.scroll_positions["files"] = 0
                    self.status_message = f"Changed to: {new_dir}"
                else:
                    self.error_message = f"Invalid directory: {input_str}"
        except:
            pass

        curses.noecho()
        curses.curs_set(0)

    def _process_current_file(self):
        """Process the current file"""
        if not self.current_file:
            self.error_message = "No file selected"
            return

        try:
            self.status_message = f"Processing {Path(self.current_file).name}..."

            # Step 1: Detection
            self.detection_result = self.inference_engine.analyze_file(
                self.current_file
            )

            # Step 2: Parsing
            self.parse_result = self.parsing_engine.parse_file(
                self.current_file, self.detection_result
            )

            # Step 3: Setup search engine
            self.search_engine.index_entries(self.parse_result.entries)

            # Step 4: Statistical analysis
            self.stats_analyzer.reset()
            self.stats_analyzer.add_detection_result(self.detection_result)
            self.stats_analyzer.add_parse_result(self.parse_result)
            self.insights = self.stats_analyzer.analyze()

            self.status_message = (
                f"Successfully processed {Path(self.current_file).name}"
            )

        except Exception as e:
            self.error_message = f"Failed to process file: {e}"

    def _execute_search(self):
        """Execute search query"""
        if not self.parse_result:
            self.error_message = "No file processed yet"
            return

        try:
            # Build search query from form
            query = self.search_form.build_query()

            # Execute search
            self.search_results = self.search_engine.search(query)
            self.scroll_positions["results"] = 0
            self.scroll_positions["field_values"] = 0

            self.status_message = f"Found {self.search_results.total_matches} matches in {self.search_results.search_time:.3f}s"

        except Exception as e:
            self.error_message = f"Search failed: {e}"


def main():
    def run_tui(stdscr):
        app = LogExplorerTUI(stdscr)

        # Handle command line arguments for initial file
        if len(sys.argv) > 1:
            initial_file = Path(sys.argv[1])
            if initial_file.exists() and initial_file.is_file():
                app.current_file = str(initial_file)
                app.current_dir = initial_file.parent
                app.refresh_dir_contents()

        app.run()

    curses.wrapper(run_tui)


if __name__ == "__main__":
    main()
