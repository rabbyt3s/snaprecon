"""Local heuristic analysis for screenshots (no external LLM)."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import List, Optional

from .errors import LLMError
from .models import Target, LLMResult
from .config import AppConfig

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """Local analyzer that tags pages based on title/URL keywords."""
    
    def __init__(self, config: AppConfig):
        self.config = config
    
    def estimate_cost(self, image_path: Path) -> float:
        """Local analysis has zero cost."""
        return 0.0
    
    def _encode_image(self, image_path: Path) -> str:
        """Encode image to base64 for Gemini API."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            raise LLMError(f"Failed to encode image {image_path}: {e}")
    
    async def analyze_screenshot(self, target: Target) -> Target:
        """Analyze a single screenshot with Gemini Vision."""
        if not target.metadata or not target.metadata.screenshot_path:
            target.error = LLMError(
                "No screenshot available for analysis",
                code="NO_SCREENSHOT"
            )
            return target
        
        image_path = target.metadata.screenshot_path
        
        try:
            # Check if image exists (not strictly needed for local keywording, but keep invariant)
            if not image_path.exists():
                target.error = LLMError(
                    f"Screenshot file not found: {image_path}",
                    code="SCREENSHOT_MISSING"
                )
                return target

            # Build text to analyze from title and URL/host
            title = (target.metadata.title or "").lower()
            url = (target.metadata.final_url or f"https://{target.host}").lower()
            host = target.host.lower()
            corpus = " ".join([title, url, host])

            # Keyword → tag mapping
            tag_map = {
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

            found_tags: List[str] = []
            for tag, kws in tag_map.items():
                if any(kw in corpus for kw in kws):
                    found_tags.append(tag)

            # Heuristic interesting score
            high = {"admin", "sso", "vpn", "monitoring", "devops", "db", "security"}
            medium = {"api", "ticketing", "mail", "analytics"}
            score = 0.3
            if any(t in found_tags for t in high):
                score = 0.9
                color = "red"
            elif any(t in found_tags for t in medium):
                score = 0.7
                color = "amber"
            else:
                color = "green"

            # Compose summary (no explicit color text; UI will render interest)
            pretty_title = target.metadata.title or "(no title)"
            summary = f"Title: {pretty_title} | URL: {target.metadata.final_url or f'https://{target.host}'}"
            tags = sorted(found_tags)
            confidence = score
            cost = 0.0

            target.llm_result = LLMResult(
                summary=summary,
                tags=tags if tags else ["unknown"],
                confidence=confidence,
                cost_usd=cost,
                model_used="local-keyword"
            )

            logger.info(f"Analysis completed for {target.host}: local (cost ${cost:.4f})")
        except Exception as e:
            logger.error(f"Failed to analyze {target.host}: {e}")
            target.error = LLMError(
                f"Analysis failed: {e}",
                code="ANALYSIS_FAILED"
            )
        
        return target
    
    async def analyze_many(self, targets: List[Target]) -> List[Target]:
        """Analyze multiple targets concurrently."""
        # Filter targets that have screenshots
        analyzable_targets = [
            target for target in targets 
            if target.metadata and target.metadata.screenshot_path and not target.error
        ]
        
        if not analyzable_targets:
            logger.warning("No targets available for analysis")
            return targets
        
        # Check cost limits
        total_estimated_cost = sum(
            self.estimate_cost(target.metadata.screenshot_path) 
            for target in analyzable_targets
        )
        
        if total_estimated_cost > self.config.max_cost_usd:
            raise LLMError(
                f"Estimated cost (${total_estimated_cost:.2f}) exceeds limit (${self.config.max_cost_usd:.2f})",
                code="COST_LIMIT_EXCEEDED"
            )
        
        # Process targets
        tasks = [self.analyze_screenshot(target) for target in analyzable_targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update original targets with results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error analyzing target {analyzable_targets[i].host}: {result}")
                analyzable_targets[i].error = LLMError(
                    f"Analysis failed: {result}",
                    code="ANALYSIS_ERROR"
                )
        
        return targets
