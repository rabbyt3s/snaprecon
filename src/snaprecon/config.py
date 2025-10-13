"""Configuration management for SnapRecon."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional, Set

from pydantic import BaseModel, Field, PrivateAttr, field_validator
import toml


class AppConfig(BaseModel):
    """Application configuration with validation."""

    _explicit_fields: Set[str] = PrivateAttr(default_factory=set)

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
    scan_profile: Literal["fast", "balanced", "full"] = Field(
        default="balanced",
        description="Preset controlling balance between speed and depth",
    )
    dry_run: bool = Field(default=False, description="Skip keyword analysis")
    debug: bool = Field(default=False, description="Enable debug logging")
    wappalyzer_enabled: bool = Field(
        default=False,
        description="Enable Wappalyzer-based technology detection",
    )
    wappalyzer_scan_type: Literal["fast", "balanced", "full"] = Field(
        default="balanced",
        description="Wappalyzer scan depth: fast, balanced, or full",
    )
    wappalyzer_threads: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Thread count for Wappalyzer HTTP probing",
    )
    
    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: Path) -> Path:
        """Ensure output directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("scan_profile", mode="before")
    @classmethod
    def normalize_profile(cls, value: object) -> Literal["fast", "balanced", "full"]:
        if value is None:
            return "balanced"
        lowered = str(value).strip().lower()
        if lowered not in {"fast", "balanced", "full"}:
            raise ValueError("Scan profile must be one of: fast, balanced, full")
        return lowered  # type: ignore[return-value]

    @field_validator("wappalyzer_enabled", mode="before")
    @classmethod
    def coerce_bool(cls, value: object) -> bool:
        """Coerce truthy representations to bool."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @field_validator("wappalyzer_scan_type", mode="before")
    @classmethod
    def normalize_scan_type(cls, value: object) -> Literal["fast", "balanced", "full"]:
        if value is None:
            return "balanced"
        if isinstance(value, str):
            lowered = value.strip().lower()
        else:
            lowered = str(value).strip().lower()
        if lowered not in {"fast", "balanced", "full"}:
            raise ValueError("Wappalyzer scan type must be one of: fast, balanced, full")
        return lowered  # type: ignore[return-value]

    @field_validator("wappalyzer_threads", mode="before")
    @classmethod
    def clamp_threads(cls, value: object) -> int:
        try:
            threads = int(value)
        except (TypeError, ValueError):
            threads = 3
        return max(1, min(20, threads))

    def _field_is_default(self, field_name: str) -> bool:
        return getattr(self, field_name) == self.__class__.model_fields[field_name].default and field_name not in self._explicit_fields

    def apply_scan_profile_defaults(self) -> None:
        """Apply preset defaults based on scan profile unless explicitly overridden."""

        profile = self.scan_profile

        if profile == "fast":
            if self._field_is_default("dry_run"):
                self.dry_run = True
            if self._field_is_default("wappalyzer_enabled"):
                self.wappalyzer_enabled = False
            if self._field_is_default("wappalyzer_scan_type"):
                self.wappalyzer_scan_type = "fast"
        elif profile == "balanced":
            if self._field_is_default("dry_run"):
                self.dry_run = False
            if self._field_is_default("wappalyzer_enabled"):
                self.wappalyzer_enabled = False
            if self._field_is_default("wappalyzer_scan_type"):
                self.wappalyzer_scan_type = "balanced"
        else:  # full
            if self._field_is_default("dry_run"):
                self.dry_run = False
            if self._field_is_default("wappalyzer_enabled"):
                self.wappalyzer_enabled = True
            if self.wappalyzer_scan_type in {
                "balanced",
                self.__class__.model_fields["wappalyzer_scan_type"].default,
            }:
                self.wappalyzer_scan_type = "full"
            if self._field_is_default("wappalyzer_threads"):
                self.wappalyzer_threads = max(self.wappalyzer_threads, 5)
    
    @classmethod
    def from_env(cls) -> AppConfig:
        """Create config from environment variables and optional config.toml."""
        def optional_env(name: str) -> Optional[str]:
            value = os.getenv(name)
            return value if value not in {None, ""} else None

        explicit: Set[str] = set()

        cfg = {
            "output_dir": Path(optional_env("SNAPRECON_OUTPUT_DIR") or "runs"),
            "user_agent": optional_env("SNAPRECON_USER_AGENT") or "",
            "timeout_ms": int(optional_env("SNAPRECON_TIMEOUT_MS") or 30000),
            "fullpage": (optional_env("SNAPRECON_FULLPAGE") or "false").lower() == "true",
            "subfinder_bin": optional_env("SNAPRECON_SUBFINDER_BIN") or "subfinder",
            "concurrency": int(optional_env("SNAPRECON_CONCURRENCY") or 5),
            "headless": (optional_env("SNAPRECON_HEADLESS") or "true").lower()
            not in {"0", "false", "no"},
            "debug": (optional_env("SNAPRECON_DEBUG") or "false").lower() == "true",
            "scan_profile": optional_env("SNAPRECON_SCAN_PROFILE") or "balanced",
            "wappalyzer_enabled": optional_env("SNAPRECON_WAPPALYZER_ENABLED"),
            "wappalyzer_scan_type": optional_env("SNAPRECON_WAPPALYZER_SCAN_TYPE") or "balanced",
            "wappalyzer_threads": int(optional_env("SNAPRECON_WAPPALYZER_THREADS") or 3),
        }

        # Record env-provided keys for explicit override tracking
        env_field_map = {
            "output_dir": "SNAPRECON_OUTPUT_DIR",
            "user_agent": "SNAPRECON_USER_AGENT",
            "timeout_ms": "SNAPRECON_TIMEOUT_MS",
            "fullpage": "SNAPRECON_FULLPAGE",
            "subfinder_bin": "SNAPRECON_SUBFINDER_BIN",
            "concurrency": "SNAPRECON_CONCURRENCY",
            "headless": "SNAPRECON_HEADLESS",
            "debug": "SNAPRECON_DEBUG",
            "scan_profile": "SNAPRECON_SCAN_PROFILE",
            "wappalyzer_enabled": "SNAPRECON_WAPPALYZER_ENABLED",
            "wappalyzer_scan_type": "SNAPRECON_WAPPALYZER_SCAN_TYPE",
            "wappalyzer_threads": "SNAPRECON_WAPPALYZER_THREADS",
        }

        for field_name, env_name in env_field_map.items():
            if os.getenv(env_name) not in {None, ""}:
                explicit.add(field_name)

        # Merge config.toml if present
        config_path = Path(os.getenv("SNAPRECON_CONFIG", "config.toml"))
        if config_path.exists():
            try:
                data = toml.loads(config_path.read_text())
                # Map sections → fields
                browser = data.get("browser", {})
                discovery = data.get("discovery", {})
                output = data.get("output", {})
                runtime = data.get("runtime", {})
                wappalyzer_cfg = data.get("wappalyzer", {})

                ua = browser.get("user_agent")
                if ua:
                    cfg["user_agent"] = ua
                    explicit.add("user_agent")
                if "timeout_ms" in browser:
                    cfg["timeout_ms"] = int(browser["timeout_ms"])
                    explicit.add("timeout_ms")
                if "fullpage" in browser:
                    cfg["fullpage"] = bool(browser["fullpage"])
                    explicit.add("fullpage")
                if "headless" in browser:
                    cfg["headless"] = bool(browser["headless"])
                    explicit.add("headless")

                if browser.get("user_agent"):
                    cfg["user_agent"] = browser["user_agent"]
                    explicit.add("user_agent")

                if discovery.get("subfinder_bin"):
                    cfg["subfinder_bin"] = discovery["subfinder_bin"]
                    explicit.add("subfinder_bin")
                if "concurrency" in discovery:
                    cfg["concurrency"] = int(discovery["concurrency"])
                    explicit.add("concurrency")

                out_dir = output.get("output_dir")
                if out_dir:
                    cfg["output_dir"] = Path(out_dir)
                    explicit.add("output_dir")
                if "debug" in output:
                    cfg["debug"] = bool(output["debug"])
                    explicit.add("debug")

                if runtime.get("scan_profile"):
                    cfg["scan_profile"] = runtime["scan_profile"]
                    explicit.add("scan_profile")
                if "dry_run" in runtime:
                    cfg["dry_run"] = bool(runtime["dry_run"])
                    explicit.add("dry_run")

                if "enabled" in wappalyzer_cfg:
                    cfg["wappalyzer_enabled"] = wappalyzer_cfg.get("enabled")
                    explicit.add("wappalyzer_enabled")
                if "scan_type" in wappalyzer_cfg:
                    cfg["wappalyzer_scan_type"] = wappalyzer_cfg.get("scan_type")
                    explicit.add("wappalyzer_scan_type")
                if "threads" in wappalyzer_cfg:
                    cfg["wappalyzer_threads"] = wappalyzer_cfg.get("threads")
                    explicit.add("wappalyzer_threads")

            except Exception:
                # Fall back silently to env/defaults if toml invalid
                pass

        config = cls(**cfg)
        config._explicit_fields.update(explicit)
        config.apply_scan_profile_defaults()
        return config
    
    @classmethod
    def from_cli(cls, **kwargs) -> AppConfig:
        """Create config from CLI arguments, merging with environment."""
        env_config = cls.from_env()

        update_data = {}
        for key, value in kwargs.items():
            if value is None or not hasattr(env_config, key):
                continue
            if key == "wappalyzer_scan_type" and isinstance(value, str):
                update_data[key] = value.lower()
            elif key == "scan_profile" and isinstance(value, str):
                update_data[key] = value.lower()
            else:
                update_data[key] = value

            env_config._explicit_fields.add(key)

        if update_data:
            env_config = env_config.model_copy(update=update_data)
        
        # Create run directory
        if env_config.run_dir is None:
            timestamp = env_config.timestamp.strftime("%Y%m%d_%H%M%S")
            env_config.run_dir = env_config.output_dir / timestamp
            env_config.run_dir.mkdir(parents=True, exist_ok=True)
        
        env_config.apply_scan_profile_defaults()

        return env_config
    
    @property
    def timestamp(self):
        """Get current timestamp for run directory naming."""
        from datetime import datetime
        return datetime.now()
    
    model_config = {"extra": "forbid", "validate_assignment": True}
