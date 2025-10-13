"""Technology fingerprinting helpers powered by Wappalyzer."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .config import AppConfig
from .models import Target, Technology

from contextlib import redirect_stdout, redirect_stderr
import io

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard exercised in runtime environments without wappalyzer
    from wappalyzer import analyze as wappalyzer_analyze  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime if dependency missing
    wappalyzer_analyze = None


def _extract_result_for_url(raw_result: dict, target_url: str) -> dict:
    """Return the technology mapping for the requested URL from Wappalyzer output."""

    if not isinstance(raw_result, dict):
        return {}

    normalized_url = target_url.rstrip("/")

    # Exact match first
    if target_url in raw_result:
        return raw_result[target_url] or {}

    if normalized_url in raw_result:
        return raw_result[normalized_url] or {}

    # Match ignoring trailing slashes across keys
    for key, value in raw_result.items():
        if isinstance(key, str) and key.rstrip("/") == normalized_url:
            return value or {}

    # Fall back to first mapping if direct key missing
    if raw_result:
        first_value = next(iter(raw_result.values()))
        if isinstance(first_value, dict):
            return first_value

    return {}


def _convert_to_models(tech_map: dict) -> list[Technology]:
    """Convert raw Wappalyzer technology dict into Technology models."""

    if not isinstance(tech_map, dict):
        return []

    technologies: list[Technology] = []
    for name, payload in tech_map.items():
        if not isinstance(payload, dict):
            continue

        try:
            technologies.append(
                Technology(
                    name=name,
                    confidence=int(payload.get("confidence", 0) or 0),
                    version=(payload.get("version") or None),
                    categories=list(payload.get("categories") or []),
                    groups=list(payload.get("groups") or []),
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Skipping invalid technology payload for %s: %s", name, exc)

    return sorted(technologies, key=lambda tech: (-tech.confidence, tech.name))


def _run_wappalyzer_analyze(url: str, scan_type: str, threads: int):
    buffered_out = io.StringIO()
    buffered_err = io.StringIO()
    with redirect_stdout(buffered_out), redirect_stderr(buffered_err):
        result = wappalyzer_analyze(url=url, scan_type=scan_type, threads=threads)
    return result, buffered_out.getvalue(), buffered_err.getvalue()


async def detect_technologies(
    targets: list[Target],
    config: AppConfig,
    *,
    progress_callback: Optional[Callable[[Target], None]] = None,
) -> list[Target]:
    """Populate targets with detected technologies using Wappalyzer."""

    if not config.wappalyzer_enabled:
        return targets

    if wappalyzer_analyze is None:
        raise RuntimeError(
            "Wappalyzer integration requested but the 'wappalyzer' package is not installed. "
            "Install snaprecon with the optional dependency (pip install wappalyzer)."
        )

    for target in targets:
        if not target.metadata or not target.metadata.final_url:
            if progress_callback:
                progress_callback(target)
            continue

        url = target.metadata.final_url
        if not url:
            url = f"https://{target.host}"

        try:
            raw_result, std_out, std_err = await asyncio.to_thread(
                _run_wappalyzer_analyze,
                url,
                config.wappalyzer_scan_type,
                config.wappalyzer_threads,
            )
            if std_out.strip():
                logger.debug("Wappalyzer stdout for %s: %s", target.host, std_out.strip())
            if std_err.strip():
                logger.debug("Wappalyzer stderr for %s: %s", target.host, std_err.strip())
            tech_map = _extract_result_for_url(raw_result, url)
            target.metadata.technologies = _convert_to_models(tech_map)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Wappalyzer scan failed for %s: %s", target.host, exc)
        finally:
            if progress_callback:
                progress_callback(target)

    return targets


__all__ = ["detect_technologies"]



