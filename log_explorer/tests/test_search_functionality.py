import pytest
from datetime import datetime, timedelta
from dataclasses import dataclass
from log_explorer.search.search_engine import (
    LogSearchEngine,
    SearchQuery,
    SearchFilter,
    TimeFilter,
    QueryBuilder,
    search_errors,
    search_by_ip,
)


@dataclass
class MockLogEntry:
    fields: dict
    raw_line: str
    timestamp: datetime = None


@pytest.fixture
def sample_entries():
    now = datetime.now()
    return [
        MockLogEntry(
            fields={
                "level": "error",
                "message": "Database connection failed",
                "status": "500",
            },
            raw_line="ERROR: Database connection failed",
            timestamp=now - timedelta(hours=1.9),
        ),
        MockLogEntry(
            fields={
                "level": "info",
                "message": "User login successful",
                "status": "200",
            },
            raw_line="INFO: User login successful",
            timestamp=now - timedelta(hours=1),
        ),
        MockLogEntry(
            fields={
                "level": "warning",
                "message": "High memory usage",
                "status": "200",
            },
            raw_line="WARN: High memory usage",
            timestamp=now - timedelta(minutes=30),
        ),
        MockLogEntry(
            fields={"level": "error", "message": "File not found", "status": "404"},
            raw_line="ERROR: File not found",
            timestamp=now - timedelta(minutes=10),
        ),
    ]


@pytest.fixture
def search_engine(sample_entries):
    engine = LogSearchEngine()
    engine.index_entries(sample_entries)
    return engine


def test_text_search(search_engine):
    query = SearchQuery(text="error")
    result = search_engine.search(query)
    assert result.total_matches == 2
    assert all(
        "error" in entry.raw_line.lower()
        or any("error" in str(v).lower() for v in entry.fields.values())
        for entry in result.entries
    )


def test_field_equals_filter(search_engine):
    filter_obj = SearchFilter("level", "error", "equals")
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 2
    assert all(entry.fields["level"] == "error" for entry in result.entries)


def test_field_contains_filter(search_engine):
    filter_obj = SearchFilter("message", "connection", "contains")
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 1
    assert "connection" in result.entries[0].fields["message"]


def test_regex_filter(search_engine):
    filter_obj = SearchFilter("status", "^[45]", "regex")
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 2
    assert all(entry.fields["status"] in ["404", "500"] for entry in result.entries)


def test_numeric_filters(search_engine):
    filter_obj = SearchFilter("status", "300", "gt")
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 2

    filter_obj = SearchFilter("status", "300", "lt")
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 2


def test_time_filter_absolute(search_engine):
    now = datetime.now()
    start_time = now - timedelta(hours=1, minutes=30)
    end_time = now - timedelta(minutes=5)

    time_filter = TimeFilter(start_time=start_time, end_time=end_time)
    query = SearchQuery(time_filter=time_filter)
    result = search_engine.search(query)
    assert result.total_matches == 3


def test_time_filter_relative(search_engine):
    time_filter = TimeFilter(last_hours=2)
    query = SearchQuery(time_filter=time_filter)
    result = search_engine.search(query)
    assert result.total_matches == 4


def test_combined_filters(search_engine):
    filter_obj = SearchFilter("level", "error", "equals")
    time_filter = TimeFilter(last_hours=1)
    query = SearchQuery(filters=[filter_obj], time_filter=time_filter)
    result = search_engine.search(query)
    assert result.total_matches == 1


def test_pagination(search_engine):
    query = SearchQuery(limit=2)
    result = search_engine.search(query)
    assert len(result.entries) == 2
    assert result.total_matches == 4

    query = SearchQuery(limit=2, offset=2)
    result = search_engine.search(query)
    assert len(result.entries) == 2


def test_case_sensitivity(search_engine):
    filter_obj = SearchFilter("message", "DATABASE", "contains", case_sensitive=True)
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 0

    filter_obj = SearchFilter("message", "DATABASE", "contains", case_sensitive=False)
    query = SearchQuery(filters=[filter_obj])
    result = search_engine.search(query)
    assert result.total_matches == 1


def test_query_builder(search_engine):
    query = QueryBuilder.simple_text("error")
    result = search_engine.search(query)
    assert result.total_matches == 2

    query = QueryBuilder.field_equals("level", "info")
    result = search_engine.search(query)
    assert result.total_matches == 1

    query = QueryBuilder.field_contains("message", "user", case_sensitive=False)
    result = search_engine.search(query)
    assert result.total_matches == 1

    query = QueryBuilder.last_hours(1)
    result = search_engine.search(query)
    assert result.total_matches == 2


def test_field_counts(search_engine):
    query = SearchQuery()
    result = search_engine.search(query)
    assert "level" in result.field_counts
    assert result.field_counts["level"]["error"] == 2
    assert result.field_counts["level"]["info"] == 1


def test_empty_search(search_engine):
    query = SearchQuery(text="nonexistent")
    result = search_engine.search(query)
    assert result.total_matches == 0
    assert len(result.entries) == 0


def test_helper_functions(search_engine):

    errors = search_errors(search_engine)
    assert len(errors) == 2

    search_engine.entries[0].fields["client_ip"] = "192.168.1.1"
    results = search_by_ip(search_engine, "192.168.1.1")
    assert len(results) == 1


def test_get_field_names(search_engine):
    field_names = search_engine.get_field_names()
    assert "level" in field_names
    assert "message" in field_names
    assert "status" in field_names


def test_get_time_range(search_engine):
    start, end = search_engine.get_time_range()
    assert start is not None
    assert end is not None
    assert start < end
