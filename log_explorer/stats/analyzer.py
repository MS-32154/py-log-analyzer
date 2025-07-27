from collections import defaultdict, Counter
from datetime import datetime, timedelta
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class TimeSeriesStats:
    timestamps: List[datetime] = field(default_factory=list)
    counts_per_hour: Dict[int, int] = field(default_factory=dict)
    counts_per_day: Dict[str, int] = field(default_factory=dict)
    peak_hour: int = 0
    peak_day: str = ""
    time_range: timedelta = None
    entries_per_second: float = 0.0


@dataclass
class FieldStats:
    name: str
    data_type: str
    extraction_rate: float
    total_extracted: int
    confidence: float
    unique_values: int
    most_common_values: List[tuple] = field(default_factory=list)
    is_timestamp: bool = False
    null_rate: float = 0.0


@dataclass
class FormatStats:
    format_type: str
    detection_confidence: float
    schema_size: int
    timestamp_fields: int
    high_confidence_fields: int
    low_confidence_fields: int
    sample_line_count: int


@dataclass
class ParsingStats:
    total_lines: int
    successfully_parsed: int
    malformed_lines: int
    success_rate: float
    average_confidence: float
    error_distribution: Dict[str, int] = field(default_factory=dict)
    field_extraction_rates: Dict[str, float] = field(default_factory=dict)


@dataclass
class LogInsights:
    format_stats: FormatStats
    parsing_stats: ParsingStats
    field_stats: List[FieldStats] = field(default_factory=list)
    time_series_stats: Optional[TimeSeriesStats] = None
    quality_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)


class LogStatsAnalyzer:

    def __init__(self):
        self.reset()

    def reset(self):
        self.detection_results = []
        self.parse_results = []
        self.log_entries = []

    def add_detection_result(self, detection_result):
        self.detection_results.append(detection_result)

    def add_parse_result(self, parse_result):
        self.parse_results.append(parse_result)
        if hasattr(parse_result, "entries"):
            self.log_entries.extend(parse_result.entries)

    def analyze(self):
        if not self.detection_results and not self.parse_results:
            return LogInsights(
                format_stats=FormatStats("unknown", 0.0, 0, 0, 0, 0, 0),
                parsing_stats=ParsingStats(0, 0, 0, 0.0, 0.0),
            )

        # Use the best detection result if multiple exist
        detection_result = (
            max(self.detection_results, key=lambda x: x.confidence)
            if self.detection_results
            else None
        )

        # Aggregate parse results if multiple exist
        parse_result = self._aggregate_parse_results() if self.parse_results else None

        format_stats = (
            self._analyze_format_detection(detection_result)
            if detection_result
            else None
        )
        parsing_stats = (
            self._analyze_parsing_performance(parse_result) if parse_result else None
        )
        field_stats = self._analyze_field_statistics(detection_result, parse_result)
        time_series_stats = self._analyze_time_series()

        quality_score = self._calculate_quality_score(format_stats, parsing_stats)
        recommendations = self._generate_recommendations(
            format_stats, parsing_stats, field_stats
        )

        return LogInsights(
            format_stats=format_stats or FormatStats("unknown", 0.0, 0, 0, 0, 0, 0),
            parsing_stats=parsing_stats or ParsingStats(0, 0, 0, 0.0, 0.0),
            field_stats=field_stats,
            time_series_stats=time_series_stats,
            quality_score=quality_score,
            recommendations=recommendations,
        )

    def _aggregate_parse_results(self):
        if not self.parse_results:
            return None

        # Combine all parse results into a single aggregated result
        total_lines = sum(r.total_lines for r in self.parse_results)
        successfully_parsed = sum(r.successfully_parsed for r in self.parse_results)
        malformed_lines = sum(r.malformed_lines for r in self.parse_results)

        # Aggregate statistics
        all_stats = {}
        for result in self.parse_results:
            if hasattr(result, "parse_statistics") and result.parse_statistics:
                for key, value in result.parse_statistics.items():
                    if key == "field_extraction_rates" and isinstance(value, dict):
                        if key not in all_stats:
                            all_stats[key] = defaultdict(list)
                        for field, rate_info in value.items():
                            if (
                                isinstance(rate_info, dict)
                                and "extraction_rate" in rate_info
                            ):
                                all_stats[key][field].append(
                                    rate_info["extraction_rate"]
                                )
                    elif key == "error_types" and isinstance(value, dict):
                        if key not in all_stats:
                            all_stats[key] = Counter()
                        all_stats[key].update(value)
                    elif key == "average_confidence":
                        if key not in all_stats:
                            all_stats[key] = []
                        all_stats[key].append(value)

        # Calculate final aggregated statistics
        final_stats = {}
        if "field_extraction_rates" in all_stats:
            final_stats["field_extraction_rates"] = {}
            for field, rates in all_stats["field_extraction_rates"].items():
                final_stats["field_extraction_rates"][field] = {
                    "extraction_rate": statistics.mean(rates),
                    "total_extracted": int(statistics.mean(rates) * total_lines),
                }

        if "error_types" in all_stats:
            final_stats["error_types"] = dict(all_stats["error_types"])

        if "average_confidence" in all_stats:
            final_stats["average_confidence"] = statistics.mean(
                all_stats["average_confidence"]
            )

        # Create a mock parse result object
        class AggregatedParseResult:
            def __init__(self):
                self.total_lines = total_lines
                self.successfully_parsed = successfully_parsed
                self.malformed_lines = malformed_lines
                self.success_rate = (
                    successfully_parsed / total_lines if total_lines > 0 else 0.0
                )
                self.parse_statistics = final_stats

        return AggregatedParseResult()

    def _analyze_format_detection(self, detection_result):
        timestamp_fields = sum(
            1 for field in detection_result.schema.values() if field.is_timestamp
        )
        high_confidence_fields = sum(
            1 for field in detection_result.schema.values() if field.confidence >= 0.8
        )
        low_confidence_fields = sum(
            1 for field in detection_result.schema.values() if field.confidence < 0.5
        )

        return FormatStats(
            format_type=detection_result.format_type.value,
            detection_confidence=detection_result.confidence,
            schema_size=len(detection_result.schema),
            timestamp_fields=timestamp_fields,
            high_confidence_fields=high_confidence_fields,
            low_confidence_fields=low_confidence_fields,
            sample_line_count=len(detection_result.sample_lines),
        )

    def _analyze_parsing_performance(self, parse_result):
        error_dist = {}
        field_rates = {}
        avg_confidence = 0.0

        if hasattr(parse_result, "parse_statistics") and parse_result.parse_statistics:
            stats = parse_result.parse_statistics

            if "error_types" in stats:
                error_dist = stats["error_types"]

            if "field_extraction_rates" in stats:
                field_rates = {
                    field: info.get("extraction_rate", 0.0)
                    for field, info in stats["field_extraction_rates"].items()
                }

            avg_confidence = stats.get("average_confidence", 0.0)

        return ParsingStats(
            total_lines=parse_result.total_lines,
            successfully_parsed=parse_result.successfully_parsed,
            malformed_lines=parse_result.malformed_lines,
            success_rate=parse_result.success_rate,
            average_confidence=avg_confidence,
            error_distribution=error_dist,
            field_extraction_rates=field_rates,
        )

    def _analyze_field_statistics(self, detection_result, parse_result):
        field_stats = []

        # Start with detection schema if available
        field_info_map = {}
        if detection_result and detection_result.schema:
            for field_name, field_info in detection_result.schema.items():
                field_info_map[field_name] = {
                    "data_type": field_info.data_type,
                    "confidence": field_info.confidence,
                    "is_timestamp": field_info.is_timestamp,
                    "sample_values": field_info.sample_values,
                }

        # Add parsing statistics
        extraction_rates = {}
        if (
            parse_result
            and hasattr(parse_result, "parse_statistics")
            and parse_result.parse_statistics
        ):
            if "field_extraction_rates" in parse_result.parse_statistics:
                for field, info in parse_result.parse_statistics[
                    "field_extraction_rates"
                ].items():
                    extraction_rates[field] = info

        # Analyze actual log entries for more detailed field stats
        field_value_counts = defaultdict(Counter)
        field_null_counts = defaultdict(int)
        total_entries = len(self.log_entries)

        for entry in self.log_entries:
            if hasattr(entry, "fields"):
                for field_name, value in entry.fields.items():
                    if value is None or value == "":
                        field_null_counts[field_name] += 1
                    else:
                        field_value_counts[field_name][value] += 1

        # Combine all field information
        all_fields = (
            set(field_info_map.keys())
            | set(extraction_rates.keys())
            | set(field_value_counts.keys())
        )

        for field_name in all_fields:
            info = field_info_map.get(field_name, {})
            extraction_info = extraction_rates.get(field_name, {})

            unique_values = len(field_value_counts[field_name])
            most_common = field_value_counts[field_name].most_common(5)
            null_rate = (
                field_null_counts[field_name] / total_entries
                if total_entries > 0
                else 0.0
            )

            field_stat = FieldStats(
                name=field_name,
                data_type=info.get("data_type", "unknown"),
                extraction_rate=extraction_info.get("extraction_rate", 0.0),
                total_extracted=extraction_info.get("total_extracted", 0),
                confidence=info.get("confidence", 0.0),
                unique_values=unique_values,
                most_common_values=most_common,
                is_timestamp=info.get("is_timestamp", False),
                null_rate=null_rate,
            )
            field_stats.append(field_stat)

        return sorted(field_stats, key=lambda x: x.extraction_rate, reverse=True)

    def _analyze_time_series(self):
        if not self.log_entries:
            return None

        timestamps = []
        for entry in self.log_entries:
            if hasattr(entry, "timestamp") and entry.timestamp:
                timestamps.append(entry.timestamp)

        if not timestamps:
            return None

        timestamps.sort()

        # Count by hour and day
        counts_per_hour = defaultdict(int)
        counts_per_day = defaultdict(int)

        for ts in timestamps:
            counts_per_hour[ts.hour] += 1
            counts_per_day[ts.strftime("%Y-%m-%d")] += 1

        peak_hour = (
            max(counts_per_hour.items(), key=lambda x: x[1])[0]
            if counts_per_hour
            else 0
        )
        peak_day = (
            max(counts_per_day.items(), key=lambda x: x[1])[0] if counts_per_day else ""
        )

        time_range = (
            timestamps[-1] - timestamps[0] if len(timestamps) > 1 else timedelta(0)
        )
        entries_per_second = (
            len(timestamps) / time_range.total_seconds()
            if time_range.total_seconds() > 0
            else 0.0
        )

        return TimeSeriesStats(
            timestamps=timestamps,
            counts_per_hour=dict(counts_per_hour),
            counts_per_day=dict(counts_per_day),
            peak_hour=peak_hour,
            peak_day=peak_day,
            time_range=time_range,
            entries_per_second=entries_per_second,
        )

    def _calculate_quality_score(self, format_stats, parsing_stats):
        if not format_stats or not parsing_stats:
            return 0.0

        # Detection quality component (0-30 points)
        detection_score = format_stats.detection_confidence * 30

        # Parsing success component (0-40 points)
        parsing_score = parsing_stats.success_rate * 40

        # Field extraction quality component (0-20 points)
        if parsing_stats.field_extraction_rates:
            avg_extraction_rate = statistics.mean(
                parsing_stats.field_extraction_rates.values()
            )
            field_score = avg_extraction_rate * 20
        else:
            field_score = 0

        # Confidence component (0-10 points)
        confidence_score = parsing_stats.average_confidence * 10

        total_score = detection_score + parsing_score + field_score + confidence_score
        return min(total_score / 100.0, 1.0)  # Normalize to 0-1

    def _generate_recommendations(self, format_stats, parsing_stats, field_stats):
        recommendations = []

        if not format_stats or not parsing_stats:
            return ["Insufficient data for analysis"]

        # Detection confidence recommendations
        if format_stats.detection_confidence < 0.7:
            recommendations.append(
                "Low format detection confidence - consider manual format specification"
            )

        # Parsing success recommendations
        if parsing_stats.success_rate < 0.8:
            recommendations.append(
                "Low parsing success rate - review malformed lines and adjust parsing rules"
            )

        # Field extraction recommendations
        poor_fields = [f for f in field_stats if f.extraction_rate < 0.5]
        if poor_fields:
            recommendations.append(
                f"Poor extraction for fields: {', '.join(f.name for f in poor_fields[:3])}"
            )

        # High null rate recommendations
        high_null_fields = [f for f in field_stats if f.null_rate > 0.3]
        if high_null_fields:
            recommendations.append(
                f"High null rates in fields: {', '.join(f.name for f in high_null_fields[:3])}"
            )

        # Schema recommendations
        if format_stats.timestamp_fields == 0:
            recommendations.append(
                "No timestamp fields detected - time-based analysis will be limited"
            )

        if format_stats.low_confidence_fields > format_stats.high_confidence_fields:
            recommendations.append(
                "Many low-confidence fields detected - consider schema validation"
            )

        # Error pattern recommendations
        if parsing_stats.error_distribution:
            most_common_error = max(
                parsing_stats.error_distribution.items(), key=lambda x: x[1]
            )
            if most_common_error[1] > parsing_stats.total_lines * 0.1:
                recommendations.append(
                    f"Frequent {most_common_error[0]} errors - review log format consistency"
                )

        return recommendations[:5]  # Limit to top 5 recommendations


class MultiFileStatsAggregator:

    def __init__(self):
        self.file_insights = {}
        self.global_stats = defaultdict(list)

    def add_file_analysis(self, filename, insights):
        self.file_insights[filename] = insights

        # Aggregate global statistics
        self.global_stats["quality_scores"].append(insights.quality_score)
        self.global_stats["detection_confidences"].append(
            insights.format_stats.detection_confidence
        )
        self.global_stats["success_rates"].append(insights.parsing_stats.success_rate)
        self.global_stats["formats"].append(insights.format_stats.format_type)

    def get_global_insights(self):
        if not self.file_insights:
            return {}

        total_files = len(self.file_insights)

        # Format distribution
        format_distribution = Counter(self.global_stats["formats"])

        # Quality metrics
        avg_quality = statistics.mean(self.global_stats["quality_scores"])
        avg_detection_confidence = statistics.mean(
            self.global_stats["detection_confidences"]
        )
        avg_success_rate = statistics.mean(self.global_stats["success_rates"])

        # Problem files identification
        problem_files = []
        for filename, insights in self.file_insights.items():
            if insights.quality_score < 0.5:
                problem_files.append(
                    {
                        "filename": filename,
                        "quality_score": insights.quality_score,
                        "main_issues": insights.recommendations[:2],
                    }
                )

        return {
            "total_files_analyzed": total_files,
            "format_distribution": dict(format_distribution),
            "average_quality_score": avg_quality,
            "average_detection_confidence": avg_detection_confidence,
            "average_success_rate": avg_success_rate,
            "problem_files": sorted(problem_files, key=lambda x: x["quality_score"]),
            "quality_distribution": {
                "excellent": sum(
                    1 for s in self.global_stats["quality_scores"] if s >= 0.9
                ),
                "good": sum(
                    1 for s in self.global_stats["quality_scores"] if 0.7 <= s < 0.9
                ),
                "fair": sum(
                    1 for s in self.global_stats["quality_scores"] if 0.5 <= s < 0.7
                ),
                "poor": sum(1 for s in self.global_stats["quality_scores"] if s < 0.5),
            },
        }

    def get_comparative_analysis(self):
        if len(self.file_insights) < 2:
            return {}

        # Compare field extraction rates across files
        all_fields = set()
        for insights in self.file_insights.values():
            all_fields.update(field.name for field in insights.field_stats)

        field_comparisons = {}
        for field_name in all_fields:
            extraction_rates = []
            for filename, insights in self.file_insights.items():
                field_stat = next(
                    (f for f in insights.field_stats if f.name == field_name), None
                )
                if field_stat:
                    extraction_rates.append((filename, field_stat.extraction_rate))

            if len(extraction_rates) > 1:
                field_comparisons[field_name] = {
                    "rates": extraction_rates,
                    "variance": (
                        statistics.variance([rate for _, rate in extraction_rates])
                        if len(extraction_rates) > 1
                        else 0
                    ),
                    "best_file": max(extraction_rates, key=lambda x: x[1])[0],
                    "worst_file": min(extraction_rates, key=lambda x: x[1])[0],
                }

        return {
            "field_extraction_variance": field_comparisons,
            "consistency_score": (
                1.0
                - statistics.mean(
                    [comp["variance"] for comp in field_comparisons.values()]
                )
                if field_comparisons
                else 1.0
            ),
        }
