"""Configuration management for SnapRecon."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, Optional, Set

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

        def record(field: str, value: Any, *, explicit_fields: Set[str], cfg_map: dict[str, Any]) -> None:
            cfg_map[field] = value
            explicit_fields.add(field)

        cfg: dict[str, Any] = {}
        explicit: Set[str] = set()

        # Environment overrides
        if (value := optional_env("SNAPRECON_OUTPUT_DIR")) is not None:
            record("output_dir", Path(value), explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_USER_AGENT")) is not None:
            record("user_agent", value, explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_TIMEOUT_MS")) is not None:
            with suppress(ValueError):
                record("timeout_ms", int(value), explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_FULLPAGE")) is not None:
            record(
                "fullpage",
                value.strip().lower() in {"1", "true", "yes", "on"},
                explicit_fields=explicit,
                cfg_map=cfg,
            )

        if (value := optional_env("SNAPRECON_SUBFINDER_BIN")) is not None:
            record("subfinder_bin", value, explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_CONCURRENCY")) is not None:
            with suppress(ValueError):
                record("concurrency", int(value), explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_HEADLESS")) is not None:
            record(
                "headless",
                value.strip().lower() not in {"0", "false", "no", "off"},
                explicit_fields=explicit,
                cfg_map=cfg,
            )

        if (value := optional_env("SNAPRECON_DEBUG")) is not None:
            record(
                "debug",
                value.strip().lower() in {"1", "true", "yes", "on"},
                explicit_fields=explicit,
                cfg_map=cfg,
            )

        if (value := optional_env("SNAPRECON_SCAN_PROFILE")) is not None:
            record("scan_profile", value, explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_WAPPALYZER_ENABLED")) is not None:
            record("wappalyzer_enabled", value, explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_WAPPALYZER_SCAN_TYPE")) is not None:
            record("wappalyzer_scan_type", value, explicit_fields=explicit, cfg_map=cfg)

        if (value := optional_env("SNAPRECON_WAPPALYZER_THREADS")) is not None:
            with suppress(ValueError):
                record("wappalyzer_threads", int(value), explicit_fields=explicit, cfg_map=cfg)

        # Merge config.toml if present
        config_path = Path(os.getenv("SNAPRECON_CONFIG", "config.toml"))
        if config_path.exists():
            try:
                data = toml.loads(config_path.read_text())

                browser = data.get("browser", {})
                discovery = data.get("discovery", {})
                output = data.get("output", {})
                runtime = data.get("runtime", {})
                wappalyzer_cfg = data.get("wappalyzer", {})

                if (ua := browser.get("user_agent")):
                    record("user_agent", ua, explicit_fields=explicit, cfg_map=cfg)
                if "timeout_ms" in browser:
                    record("timeout_ms", int(browser["timeout_ms"]), explicit_fields=explicit, cfg_map=cfg)
                if "fullpage" in browser:
                    record("fullpage", bool(browser["fullpage"]), explicit_fields=explicit, cfg_map=cfg)
                if "headless" in browser:
                    record("headless", bool(browser["headless"]), explicit_fields=explicit, cfg_map=cfg)

                if discovery.get("subfinder_bin"):
                    record("subfinder_bin", discovery["subfinder_bin"], explicit_fields=explicit, cfg_map=cfg)
                if "concurrency" in discovery:
                    record("concurrency", int(discovery["concurrency"]), explicit_fields=explicit, cfg_map=cfg)

                if (out_dir := output.get("output_dir")):
                    record("output_dir", Path(out_dir), explicit_fields=explicit, cfg_map=cfg)
                if "debug" in output:
                    record("debug", bool(output["debug"]), explicit_fields=explicit, cfg_map=cfg)

                if runtime.get("scan_profile"):
                    record("scan_profile", runtime["scan_profile"], explicit_fields=explicit, cfg_map=cfg)
                if "dry_run" in runtime:
                    record("dry_run", bool(runtime["dry_run"]), explicit_fields=explicit, cfg_map=cfg)

                if "enabled" in wappalyzer_cfg:
                    record("wappalyzer_enabled", wappalyzer_cfg.get("enabled"), explicit_fields=explicit, cfg_map=cfg)
                if "scan_type" in wappalyzer_cfg:
                    record("wappalyzer_scan_type", wappalyzer_cfg.get("scan_type"), explicit_fields=explicit, cfg_map=cfg)
                if "threads" in wappalyzer_cfg:
                    record("wappalyzer_threads", wappalyzer_cfg.get("threads"), explicit_fields=explicit, cfg_map=cfg)

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
