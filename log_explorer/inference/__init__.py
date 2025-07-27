"""
Log Schema Inference Engine

A sophisticated, modular system for analyzing and inferring schemas from various log formats.

This package provides:
- Automatic detection of log formats (JSON, CSV, Syslog, Apache, Nginx, etc.)
- Schema extraction with field types and confidence scores
- Support for compressed files (.gz, .bz2, .xz, .lzma)
- Timestamp detection and format inference
- Extensible detector architecture

Basic usage:
    from inference_engine import LogSchemaInferenceEngine

    engine = LogSchemaInferenceEngine()
    result = engine.analyze_lines(json_lines)

    Or from file:
    result = engine.analyze_file("path/to/logfile.log")

    print(f"Detected format: {result.format_type.value}")
    print(f"Confidence: {result.confidence}")
    for field_name, field_info in result.schema.items():
        print(f"  {field_name}: {field_info.data_type}")
"""
