"""Keyword-only analysis helpers for SnapRecon."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .models import AnalysisResult, Error, Target

logger = logging.getLogger(__name__)

KEYWORD_TAGS: dict[str, list[str]] = {
    "login": ["login", "connexion", "sign in", "auth"],
    "admin": ["admin", "administrator", "backoffice", "wp-admin"],
    "sso": ["sso", "single sign-on", "keycloak", "auth0"],
    "vpn": ["vpn", "ipsec", "anyconnect"],
    "monitoring": ["grafana", "prometheus", "zabbix", "kibana", "elastic"],
    "devops": ["jenkins", "gitlab", "harbor", "argocd", "kubernetes", "minio"],
    "storage": ["minio", "s3", "nexus"],
    "ticketing": ["jira", "servicedesk", "freshservice"],
    "docs": ["confluence", "wiki", "docs"],
    "mail": ["owa", "exchange", "zimbra", "roundcube"],
    "analytics": ["metabase", "superset", "tableau"],
    "shop": ["store", "shop", "e-commerce", "product"],
    "api": ["api", "swagger", "openapi"],
    "db": ["phpmyadmin", "pgadmin", "mongodb", "redis"],
    "security": ["vault", "guard", "shield"],
    "cms": ["wordpress", "drupal", "joomla"],
}

HIGH_VALUE_TAGS = {"admin", "sso", "vpn", "monitoring", "devops", "db", "security"}
MEDIUM_VALUE_TAGS = {"api", "ticketing", "mail", "analytics"}


def analyze_target(target: Target) -> Target:
    """Analyze a single target using simple keyword heuristics."""
    if not target.metadata or not target.metadata.screenshot_path:
        target.error = Error(message="No screenshot available for analysis", code="NO_SCREENSHOT")
        return target

    image_path = target.metadata.screenshot_path
    if not image_path.exists():
        target.error = Error(message=f"Screenshot file not found: {image_path}", code="SCREENSHOT_MISSING")
        return target

    title = (target.metadata.title or "").lower()
    url = (target.metadata.final_url or f"https://{target.host}").lower()
    host = target.host.lower()
    corpus = " ".join([title, url, host])

    found_tags: list[str] = [tag for tag, kws in KEYWORD_TAGS.items() if any(kw in corpus for kw in kws)]

    score = 0.3
    if any(tag in found_tags for tag in HIGH_VALUE_TAGS):
        score = 0.9
    elif any(tag in found_tags for tag in MEDIUM_VALUE_TAGS):
        score = 0.7

    pretty_title = target.metadata.title or "(no title)"
    summary = f"Title: {pretty_title} | URL: {target.metadata.final_url or f'https://{target.host}'}"

    target.analysis = AnalysisResult(
        summary=summary,
        tags=sorted(found_tags) if found_tags else ["unknown"],
        confidence=score,
    )
    target.error = None

    logger.debug("Analysis completed for %s", target.host)
    return target


async def analyze_targets(
    targets: list[Target],
    *,
    progress_callback: Optional[Callable[[Target], None]] = None,
) -> list[Target]:
    """Analyze each target in-place using simple keyword heuristics."""
    for target in targets:
        try:
            await asyncio.to_thread(analyze_target, target)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Analysis failed for %s", target.host)
            target.error = Error(message=f"Analysis failed: {exc}", code="ANALYSIS_FAILED")
        if progress_callback:
            progress_callback(target)
    return targets


__all__ = ["analyze_target", "analyze_targets"]
