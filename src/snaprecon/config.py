"""Configuration management for SnapRecon."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
import toml


class AppConfig(BaseModel):
    """Application configuration with validation."""
    
    # Output settings
    output_dir: Path = Field(default=Path("runs"), description="Output directory for results")
    run_dir: Optional[Path] = Field(None, description="Current run directory")
    
    # Browser settings
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User agent string"
    )
    timeout_ms: int = Field(default=30000, ge=1000, description="Page timeout in milliseconds")
    fullpage: bool = Field(default=False, description="Take full page screenshots")
    
    # Discovery settings
    subfinder_bin: str = Field(default="subfinder", description="Path to subfinder binary")
    concurrency: int = Field(default=5, ge=1, le=20, description="Concurrent operations")
    headless: bool = Field(default=True, description="Run Chromium in headless mode")
    
    # Runtime flags
    dry_run: bool = Field(default=False, description="Skip keyword analysis")
    debug: bool = Field(default=False, description="Enable debug logging")
    
    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: Path) -> Path:
        """Ensure output directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    @classmethod
    def from_env(cls) -> AppConfig:
        """Create config from environment variables and optional config.toml."""
        # Start with defaults/env
        cfg = {
            "output_dir": Path(os.getenv("SNAPRECON_OUTPUT_DIR", "runs")),
            "user_agent": os.getenv("SNAPRECON_USER_AGENT", ""),
            "timeout_ms": int(os.getenv("SNAPRECON_TIMEOUT_MS", "30000")),
            "fullpage": os.getenv("SNAPRECON_FULLPAGE", "").lower() == "true",
            "subfinder_bin": os.getenv("SNAPRECON_SUBFINDER_BIN", "subfinder"),
            "concurrency": int(os.getenv("SNAPRECON_CONCURRENCY", "5")),
            "headless": os.getenv("SNAPRECON_HEADLESS", "true").lower() not in {"0", "false", "no"},
            "debug": os.getenv("SNAPRECON_DEBUG", "").lower() == "true",
        }
        # Merge config.toml if present
        config_path = Path(os.getenv("SNAPRECON_CONFIG", "config.toml"))
        if config_path.exists():
            try:
                data = toml.loads(config_path.read_text())
                # Map sections → fields
                browser = data.get("browser", {})
                discovery = data.get("discovery", {})
                output = data.get("output", {})

                ua = browser.get("user_agent")
                if ua:
                    cfg["user_agent"] = ua
                cfg["timeout_ms"] = int(browser.get("timeout_ms", cfg["timeout_ms"]))
                cfg["fullpage"] = bool(browser.get("fullpage", cfg["fullpage"]))
                cfg["headless"] = bool(browser.get("headless", cfg["headless"]))

                cfg["subfinder_bin"] = discovery.get("subfinder_bin", cfg["subfinder_bin"]) or cfg["subfinder_bin"]
                cfg["concurrency"] = int(discovery.get("concurrency", cfg["concurrency"]))

                out_dir = output.get("output_dir")
                if out_dir:
                    cfg["output_dir"] = Path(out_dir)
                cfg["debug"] = bool(output.get("debug", cfg["debug"]))

            except Exception:
                # Fall back silently to env/defaults if toml invalid
                pass

        return cls(**cfg)
    
    @classmethod
    def from_cli(cls, **kwargs) -> AppConfig:
        """Create config from CLI arguments, merging with environment."""
        env_config = cls.from_env()
        
        # Override with CLI values
        for key, value in kwargs.items():
            if value is not None and hasattr(env_config, key):
                setattr(env_config, key, value)
        
        # Create run directory
        if env_config.run_dir is None:
            timestamp = env_config.timestamp.strftime("%Y%m%d_%H%M%S")
            env_config.run_dir = env_config.output_dir / timestamp
            env_config.run_dir.mkdir(parents=True, exist_ok=True)
        
        return env_config
    
    @property
    def timestamp(self):
        """Get current timestamp for run directory naming."""
        from datetime import datetime
        return datetime.now()
    
    model_config = {"extra": "forbid"}
