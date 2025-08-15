"""Gemini Vision analysis for screenshot content."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import List, Optional

from google import genai

from .errors import LLMError
from .models import Target, LLMResult
from .config import AppConfig

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """Analyzes screenshots using Gemini Vision."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = genai.Client(api_key=config.google_api_key)
        
        # Pricing per 1K tokens (approximate)
        self.pricing = {
            "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
            "gemini-1.5-pro": {"input": 0.375, "output": 1.50},
            "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
            "gemini-2.5-flash": {"input": 0.075, "output": 0.30},  # Added 2.5-flash
        }
    
    def estimate_cost(self, image_path: Path) -> float:
        """Estimate cost for analyzing an image."""
        # Rough estimate: assume 1K tokens for input, 500 for output
        model_pricing = self.pricing.get(self.config.gemini_model, self.pricing["gemini-1.5-flash"])
        estimated_cost = (model_pricing["input"] + model_pricing["output"] * 0.5) / 1000
        return estimated_cost
    
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
            # Check if image exists
            if not image_path.exists():
                target.error = LLMError(
                    f"Screenshot file not found: {image_path}",
                    code="SCREENSHOT_MISSING"
                )
                return target
            
            # Encode image
            image_data = self._encode_image(image_path)
            
            # Prepare prompt with structured format
            prompt = f"""
            Analyze this screenshot of {target.host} and provide a structured response:

            SUMMARY: [Brief description of what you see, max 100 words]
            TAGS: [comma-separated list of relevant categories like: login, dashboard, error, blog, e-commerce, admin, api, form, etc.]
            CONFIDENCE: [Your confidence level from 0.0 to 1.0]

            Focus on identifying the type of page, any forms, content structure, and potential security implications.
            """
            
            # Create content with image using proper Gemini API structure
            # Based on the documentation, we need to use types.Part.from_bytes()
            from google.genai import types
            
            # Create the image part using the proper API
            image_part = types.Part.from_bytes(
                data=base64.b64decode(image_data),  # Convert base64 string back to bytes
                mime_type="image/png"
            )
            
            # Create content parts with proper structure
            content_parts = [
                prompt,
                image_part
            ]
            
            # Generate content using the Gemini API
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.config.gemini_model,
                contents=content_parts
            )
            
            # Parse response with improved logic
            content = response.text.strip()
            logger.debug(f"Raw Gemini response for {target.host}: {content}")
            
            # Extract summary, tags, and confidence with better parsing
            summary = ""
            tags = []
            confidence = 0.8  # Default confidence
            
            # Look for structured response patterns
            if "SUMMARY:" in content:
                summary_start = content.find("SUMMARY:") + 8
                summary_end = content.find("TAGS:") if "TAGS:" in content else len(content)
                summary = content[summary_start:summary_end].strip()
            
            if "TAGS:" in content:
                tags_start = content.find("TAGS:") + 5
                tags_end = content.find("CONFIDENCE:") if "CONFIDENCE:" in content else len(content)
                tags_text = content[tags_start:tags_end].strip()
                tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
            
            if "CONFIDENCE:" in content:
                conf_start = content.find("CONFIDENCE:") + 11
                conf_text = content[conf_start:].strip()
                try:
                    confidence = float(conf_text)
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0,1]
                except ValueError:
                    pass
            
            # Fallback parsing if structured format not found
            if not summary or not tags:
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith("Summary:") or line.startswith("1."):
                        summary = line.split(":", 1)[1].strip() if ":" in line else line[2:].strip()
                    elif line.startswith("Tags:") or line.startswith("2."):
                        tag_part = line.split(":", 1)[1].strip() if ":" in line else line[2:].strip()
                        tags = [tag.strip() for tag in tag_part.split(",") if tag.strip()]
                    elif line.startswith("Confidence:") or line.startswith("3."):
                        try:
                            conf_part = line.split(":", 1)[1].strip() if ":" in line else line[2:].strip()
                            confidence = float(conf_part)
                            confidence = max(0.0, min(1.0, confidence))
                        except ValueError:
                            pass
            
            # Calculate cost
            cost = self.estimate_cost(image_path)
            
            # Ensure we have valid data
            if not summary or summary.strip() == "":
                summary = "Analysis completed - no summary available"
            
            if not tags or len(tags) == 0:
                tags = ["unknown"]
            
            # Create LLM result
            target.llm_result = LLMResult(
                summary=summary,
                tags=tags,
                confidence=confidence,
                cost_usd=cost,
                model_used=self.config.gemini_model
            )
            
            logger.info(f"Analysis completed for {target.host}: {cost:.4f} USD")
            logger.debug(f"Parsed results - Summary: '{summary[:50]}...', Tags: {tags}, Confidence: {confidence}")
            
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
