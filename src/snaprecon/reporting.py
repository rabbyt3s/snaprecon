"""Reporting and output generation for SnapRecon."""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional

import orjson
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import AppConfig
from .models import RunResult

logger = logging.getLogger(__name__)


def write_results_json(results: RunResult, config: AppConfig) -> Path:
    """Write results to JSON file."""
    output_file = config.run_dir / "results.json"
    
    try:
        # Convert to dict and serialize with orjson
        data = results.model_dump()
        
        # Convert PosixPath objects to strings for JSON serialization
        def convert_paths(obj):
            if isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            elif isinstance(obj, Path):
                return str(obj)
            else:
                return obj
        
        # Convert all paths to strings
        data = convert_paths(data)
        
        # Use orjson for fast serialization
        json_bytes = orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2 if config.debug else orjson.OPT_NAIVE_UTC
        )
        
        with open(output_file, "wb") as f:
            f.write(json_bytes)
        
        logger.debug(f"Results written to: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Failed to write results JSON: {e}")
        raise


_JINJA_ENV: Environment | None = None


def _get_environment() -> Environment:
    global _JINJA_ENV
    if _JINJA_ENV is None:
        # Try packaged templates first, fallback to project templates
        try:
            template_root = resources.files("snaprecon") / "templates"
            if not template_root.exists():
                raise FileNotFoundError("Packaged templates not found")
        except (FileNotFoundError, ModuleNotFoundError):
            # Fallback to project templates directory
            template_root = Path(__file__).parent.parent.parent / "templates"
        
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=select_autoescape()
        )
    return _JINJA_ENV


def render_report_template(template_name: str, results: RunResult, config: AppConfig, *, ports_map: Optional[Dict[str, List[int]]] = None, scanned_ports: Optional[List[int]] = None) -> str:
    """Render a report template with Jinja2."""

    env = _get_environment()
    template = env.get_template(template_name)

    context = {
        "results": results,
        "config": results.config,
        "success_count": len([t for t in results.targets if not t.error]),
        "error_count": len([t for t in results.targets if t.error]),
        "targets_by_status": {
            "success": [t for t in results.targets if not t.error],
            "error": [t for t in results.targets if t.error]
        },
        "ports_map": ports_map,
        "scanned_ports": scanned_ports,
    }

    return template.render(**context)


def write_markdown_report(results: RunResult, config: AppConfig) -> Path:
    """Write markdown report."""
    output_file = config.run_dir / "report.md"
    
    try:
        content = render_report_template("report.md.j2", results, config)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.debug(f"Markdown report written to: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Failed to write markdown report: {e}")
        raise


def write_html_report(results: RunResult, config: AppConfig, *, ports_map: Optional[Dict[str, List[int]]] = None, scanned_ports: Optional[List[int]] = None) -> Path:
    """Write HTML report."""
    output_file = config.run_dir / "report.html"
    
    try:
        content = render_report_template("report.html.j2", results, config, ports_map=ports_map, scanned_ports=scanned_ports)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.debug(f"HTML report written to: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Failed to write HTML report: {e}")
        raise


def write_results_and_reports(results: RunResult, config: AppConfig, *, ports_map: Optional[Dict[str, List[int]]] = None, scanned_ports: Optional[List[int]] = None) -> dict:
    """Write all output files and return paths."""
    output_files = {}
    
    try:
        # Write JSON results
        output_files["results_json"] = write_results_json(results, config)
        
        # Write reports
        output_files["markdown_report"] = write_markdown_report(results, config)
        output_files["html_report"] = write_html_report(results, config, ports_map=ports_map, scanned_ports=scanned_ports)
        
        logger.debug(f"All reports written to: {config.run_dir}")
        return output_files
        
    except Exception as e:
        logger.error(f"Failed to write reports: {e}")
        return output_files


def create_summary_stats(results: RunResult) -> dict:
    """Create summary statistics for the run."""
    targets = results.targets
    
    stats = {
        "total_targets": len(targets),
        "successful_screenshots": len([t for t in targets if t.metadata and t.metadata.screenshot_path]),
        "failed_screenshots": len([t for t in targets if t.error]),
        "successful_analyses": len([t for t in targets if t.analysis]),
        "average_confidence": 0.0,
        "top_tags": []
    }
    
    # Calculate average confidence
    confidences = [t.analysis.confidence for t in targets if t.analysis]
    if confidences:
        stats["average_confidence"] = sum(confidences) / len(confidences)
    
    # Get top tags
    all_tags = []
    for target in targets:
        if target.analysis:
            all_tags.extend(target.analysis.tags)
    
    if all_tags:
        from collections import Counter
        tag_counts = Counter(all_tags)
        stats["top_tags"] = [tag for tag, count in tag_counts.most_common(10)]
    
    return stats
