import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class SearchFilter:
    field_name: str = None
    value: str = None
    operator: str = "contains"  # contains, equals, regex, gt, lt, gte, lte
    case_sensitive: bool = False


@dataclass
class TimeFilter:
    start_time: datetime = None
    end_time: datetime = None
    last_hours: int = None
    last_minutes: int = None


@dataclass
class SearchQuery:
    text: str = None
    filters: list = field(default_factory=list)
    time_filter: TimeFilter = None
    limit: int = None
    offset: int = 0


@dataclass
class SearchResult:
    entries: list
    total_matches: int
    search_time: float
    query: SearchQuery
    field_counts: dict = field(default_factory=dict)


class LogSearchEngine:

    def __init__(self):
        self.entries = []
        self.field_index = defaultdict(list)
        self.timestamp_index = []

    def index_entries(self, entries):
        self.entries = entries
        self._build_field_index()
        self._build_timestamp_index()

    def _build_field_index(self):
        self.field_index.clear()
        for i, entry in enumerate(self.entries):
            if hasattr(entry, "fields"):
                for field_name, value in entry.fields.items():
                    if value is not None:
                        self.field_index[field_name].append((i, str(value).lower()))

    def _build_timestamp_index(self):
        self.timestamp_index = []
        for i, entry in enumerate(self.entries):
            if hasattr(entry, "timestamp") and entry.timestamp:
                self.timestamp_index.append((i, entry.timestamp))
        self.timestamp_index.sort(key=lambda x: x[1])

    def search(self, query):
        start_time = datetime.now()

        if not self.entries:
            return SearchResult([], 0, 0.0, query)

        matches = set(range(len(self.entries)))

        # Apply text search
        if query.text:
            text_matches = self._text_search(query.text)
            matches &= text_matches

        # Apply field filters
        for filter_obj in query.filters:
            filter_matches = self._apply_filter(filter_obj)
            matches &= filter_matches

        # Apply time filter
        if query.time_filter:
            time_matches = self._apply_time_filter(query.time_filter)
            matches &= time_matches

        # Convert to sorted list
        matches = sorted(list(matches), key=lambda x: x)

        # Apply pagination
        total_matches = len(matches)
        if query.offset:
            matches = matches[query.offset :]
        if query.limit:
            matches = matches[: query.limit]

        # Get actual entries
        result_entries = [self.entries[i] for i in matches]

        # Calculate field counts for faceting
        field_counts = self._calculate_field_counts(result_entries)

        search_time = (datetime.now() - start_time).total_seconds()

        return SearchResult(
            result_entries, total_matches, search_time, query, field_counts
        )

    def _text_search(self, text):
        matches = set()
        text_lower = text.lower()

        for i, entry in enumerate(self.entries):
            # Search in raw line
            if hasattr(entry, "raw_line") and text_lower in entry.raw_line.lower():
                matches.add(i)
                continue

            # Search in fields
            if hasattr(entry, "fields"):
                for value in entry.fields.values():
                    if value and text_lower in str(value).lower():
                        matches.add(i)
                        break

        return matches

    def _apply_filter(self, filter_obj):
        matches = set()

        if filter_obj.field_name not in self.field_index:
            return matches

        for entry_idx, field_value in self.field_index[filter_obj.field_name]:
            if self._match_filter(field_value, filter_obj):
                matches.add(entry_idx)

        return matches

    def _match_filter(self, field_value, filter_obj):
        target = filter_obj.value

        if not filter_obj.case_sensitive:
            target = target.lower()
        else:
            field_value = self.entries[0].fields.get(filter_obj.field_name, "")

        if filter_obj.operator == "contains":
            return target in field_value
        elif filter_obj.operator == "equals":
            return target == field_value
        elif filter_obj.operator == "regex":
            try:
                flags = 0 if filter_obj.case_sensitive else re.IGNORECASE
                return bool(re.search(target, field_value, flags))
            except re.error:
                return False
        elif filter_obj.operator in ["gt", "lt", "gte", "lte"]:
            return self._numeric_compare(field_value, target, filter_obj.operator)

        return False

    def _numeric_compare(self, field_value, target, operator):
        try:
            field_num = float(field_value)
            target_num = float(target)

            if operator == "gt":
                return field_num > target_num
            elif operator == "lt":
                return field_num < target_num
            elif operator == "gte":
                return field_num >= target_num
            elif operator == "lte":
                return field_num <= target_num
        except (ValueError, TypeError):
            pass

        return False

    def _apply_time_filter(self, time_filter):
        matches = set()

        start_time = time_filter.start_time
        end_time = time_filter.end_time

        # Handle relative time filters
        if time_filter.last_hours:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=time_filter.last_hours)
        elif time_filter.last_minutes:
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=time_filter.last_minutes)

        if not start_time and not end_time:
            return set(range(len(self.entries)))

        for entry_idx, timestamp in self.timestamp_index:
            if start_time and timestamp < start_time:
                continue
            if end_time and timestamp > end_time:
                break
            matches.add(entry_idx)

        return matches

    def _calculate_field_counts(self, entries):
        field_counts = defaultdict(lambda: defaultdict(int))

        for entry in entries:
            if hasattr(entry, "fields"):
                for field_name, value in entry.fields.items():
                    if value is not None:
                        field_counts[field_name][str(value)] += 1

        # Convert to regular dict and limit top values
        result = {}
        for field_name, value_counts in field_counts.items():
            sorted_counts = sorted(
                value_counts.items(), key=lambda x: x[1], reverse=True
            )
            result[field_name] = dict(sorted_counts[:10])  # Top 10 values

        return result

    def get_field_names(self):
        return list(self.field_index.keys())

    def get_time_range(self):
        if not self.timestamp_index:
            return None, None
        return self.timestamp_index[0][1], self.timestamp_index[-1][1]


class QueryBuilder:

    @staticmethod
    def simple_text(text, limit=None):
        return SearchQuery(text=text, limit=limit)

    @staticmethod
    def field_equals(field_name, value, limit=None):
        filter_obj = SearchFilter(field_name, value, "equals")
        return SearchQuery(filters=[filter_obj], limit=limit)

    @staticmethod
    def field_contains(field_name, value, case_sensitive=False, limit=None):
        filter_obj = SearchFilter(field_name, value, "contains", case_sensitive)
        return SearchQuery(filters=[filter_obj], limit=limit)

    @staticmethod
    def regex_search(field_name, pattern, case_sensitive=False, limit=None):
        filter_obj = SearchFilter(field_name, pattern, "regex", case_sensitive)
        return SearchQuery(filters=[filter_obj], limit=limit)

    @staticmethod
    def time_range(start_time, end_time, limit=None):
        time_filter = TimeFilter(start_time=start_time, end_time=end_time)
        return SearchQuery(time_filter=time_filter, limit=limit)

    @staticmethod
    def last_hours(hours, limit=None):
        time_filter = TimeFilter(last_hours=hours)
        return SearchQuery(time_filter=time_filter, limit=limit)

    @staticmethod
    def combined(text=None, filters=None, time_filter=None, limit=None, offset=0):
        return SearchQuery(
            text=text,
            filters=filters or [],
            time_filter=time_filter,
            limit=limit,
            offset=offset,
        )


# Usage helpers
def search_errors(search_engine, limit=100):
    filters = [
        SearchFilter("level", "error", "equals", False),
        SearchFilter("severity", "error", "equals", False),
        SearchFilter("status", "5", "contains", False),  # HTTP 5xx errors
    ]

    results = []
    for filter_obj in filters:
        query = SearchQuery(filters=[filter_obj], limit=limit)
        result = search_engine.search(query)
        results.extend(result.entries)

    # Remove duplicates while preserving order
    seen = set()
    unique_results = []
    for entry in results:
        entry_id = id(entry)
        if entry_id not in seen:
            seen.add(entry_id)
            unique_results.append(entry)

    return unique_results[:limit]


def search_by_ip(search_engine, ip_address, limit=100):
    filters = [
        SearchFilter("client_ip", ip_address, "equals"),
        SearchFilter("remote_addr", ip_address, "equals"),
        SearchFilter("ip", ip_address, "equals"),
    ]

    for filter_obj in filters:
        query = SearchQuery(filters=[filter_obj], limit=limit)
        result = search_engine.search(query)
        if result.entries:
            return result.entries

    # Fallback to text search
    query = SearchQuery(text=ip_address, limit=limit)
    return search_engine.search(query).entries
