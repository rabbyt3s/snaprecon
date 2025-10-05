"""Data models for SnapRecon with strict validation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class Error(BaseModel):
    """Error information for failed operations."""
    
    message: str = Field(..., description="Human-readable error message")
    code: Optional[str] = Field(None, description="Error code if applicable")
    details: Optional[dict] = Field(None, description="Additional error context")
    
    model_config = {"extra": "forbid"}


class Metadata(BaseModel):
    """Metadata about a target."""
    
    title: Optional[str] = Field(None, description="Page title")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    final_url: Optional[str] = Field(None, description="Final URL after redirects")
    screenshot_path: Optional[Path] = Field(None, description="Path to screenshot file")
    screenshot_size: Optional[int] = Field(None, description="Screenshot file size in bytes")
    load_time_ms: Optional[int] = Field(None, description="Page load time in milliseconds")
    
    model_config = {"extra": "forbid"}


class AnalysisResult(BaseModel):
    """Result from local keyword analysis."""

    summary: str = Field(..., description="Brief summary of the page content")
    tags: List[str] = Field(default_factory=list, description="Categorized tags")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in analysis (0-1)")

    model_config = {"extra": "forbid"}


class Target(BaseModel):
    """A target host to analyze."""
    
    host: str = Field(..., description="Hostname to analyze")
    domain: str = Field(..., description="Root domain")
    subdomain: Optional[str] = Field(None, description="Subdomain if applicable")
    metadata: Metadata = Field(default_factory=Metadata)
    analysis: Optional[AnalysisResult] = Field(None, description="Analysis result if available")
    error: Optional[Error] = Field(None, description="Error if processing failed")
    
    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Ensure host is valid."""
        if not v or "." not in v:
            raise ValueError("Host must be a valid domain")
        return v.lower().strip()
    
    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Ensure domain is valid."""
        if not v or "." not in v:
            raise ValueError("Domain must be a valid domain")
        return v.lower().strip()
    
    model_config = {"extra": "forbid"}


class SafeConfig(BaseModel):
    """Safe configuration for storing in results (excludes sensitive data)."""
    
    output_dir: str = Field(..., description="Output directory for results")
    run_dir: str = Field(..., description="Current run directory")
    user_agent: str = Field(..., description="User agent string")
    timeout_ms: int = Field(..., description="Page timeout in milliseconds")
    fullpage: bool = Field(..., description="Take full page screenshots")
    subfinder_bin: str = Field(..., description="Path to subfinder binary")
    concurrency: int = Field(..., description="Concurrent operations")
    dry_run: bool = Field(..., description="Skip keyword analysis")
    debug: bool = Field(..., description="Enable debug logging")
    headless: bool = Field(..., description="Run Chromium in headless mode")
    
    model_config = {"extra": "forbid"}


class RunResult(BaseModel):
    """Complete results from a SnapRecon run."""
    
    run_id: UUID = Field(default_factory=uuid4, description="Unique run identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Run start time")
    config: SafeConfig = Field(..., description="Safe configuration used for this run")
    targets: List[Target] = Field(default_factory=list, description="Processed targets")
    success_count: int = Field(0, ge=0, description="Number of successful analyses")
    error_count: int = Field(0, ge=0, description="Number of failed analyses")
    
    @field_validator("targets")
    @classmethod
    def validate_targets(cls, v: List[Target]) -> List[Target]:
        """Ensure targets list is not empty."""
        if not v:
            raise ValueError("At least one target must be provided")
        return v
    
    model_config = {"extra": "forbid"}
