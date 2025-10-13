"""Utility functions for SnapRecon."""

from __future__ import annotations

import hashlib
import importlib
import logging
import shutil
import subprocess
import time
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:  # pragma: no cover - import guard exercised in packaging/runtime setups
    from playwright.async_api import Error as PlaywrightError, async_playwright
except ImportError:  # pragma: no cover
    PlaywrightError = None  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]

from .errors import DependencyError

logger = logging.getLogger(__name__)


def setup_logging(debug: bool = False, log_file: Optional[Path] = None) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.CRITICAL
    
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.CRITICAL)
    console_handler.setFormatter(formatter)
    
    # Set up file handler if specified
    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True
    )


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem operations."""
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"
    
    return filename


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate hash of a file."""
    try:
        hash_obj = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        return ""


def is_valid_domain(domain: str) -> bool:
    """Check if a string is a valid domain."""
    if not domain or "." not in domain:
        return False
    
    # Basic domain validation
    parts = domain.split(".")
    if len(parts) < 2:
        return False
    
    # Check each part
    for part in parts:
        if not part or len(part) > 63:
            return False
        if not part.replace("-", "").isalnum():
            return False
        if part.startswith("-") or part.endswith("-"):
            return False
    
    return True


def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return None


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)


def format_bytes(bytes_value: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} TB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge configuration dictionaries with override taking precedence."""
    merged = base_config.copy()
    
    for key, value in override_config.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    
    return merged


def ensure_directory(path: Path) -> Path:
    """Ensure directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_extension(file_path: Path) -> str:
    """Get file extension without dot."""
    return file_path.suffix.lstrip(".")


def is_image_file(file_path: Path) -> bool:
    """Check if file is an image based on extension."""
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    return get_file_extension(file_path).lower() in image_extensions


def which(binary: str) -> Optional[str]:
    """Return the path of an executable if it exists on PATH."""

    if not binary:
        return None

    resolved = shutil.which(binary)
    if resolved:
        return str(Path(resolved))
    return None


def _missing_playwright_message() -> str:
    return (
        "Playwright or Chromium runtime is missing. Install dependencies with "
        "'pip install playwright' and 'playwright install --with-deps chromium'."
    )


def _missing_subfinder_message(binary: str) -> str:
    return (
        f"Required discovery tool not found: {binary}. Install subfinder via your package manager "
        "or provide an explicit --subfinder-bin path."
    )


def _missing_wappalyzer_message() -> str:
    return (
        "Wappalyzer integration requested but the 'wappalyzer' Python package is not installed. "
        "Install snaprecon with the optional wappalyzer extra."
    )


_PLAYWRIGHT_OK = False
_WAPPALYZER_OK = False


def _probe_chromium_launch(*, playwright_path: str, headless: bool) -> None:
    """Attempt to launch Chromium once to ensure runtime availability."""

    if async_playwright is None or PlaywrightError is None:
        raise DependencyError(_missing_playwright_message())

    command = [sys.executable, "-c"]
    script = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.launch(headless=True)\n"
        "    browser.close()\n"
    )

    try:
        subprocess.run(
            command + [script],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise DependencyError(
            "Chromium runtime binaries are missing. Run 'playwright install --with-deps chromium'."
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise DependencyError(
            "Chromium launch failed. Enable DEBUG=pw:api for details, then rerun 'playwright install chromium'."
        ) from exc


def check_required_dependencies(*, subfinder_bin: str, headless: bool) -> None:
    """Ensure required external executables and runtime assets are available."""

    missing: list[str] = []

    if which(subfinder_bin) is None:
        missing.append(_missing_subfinder_message(subfinder_bin))

    playwright_path = which("playwright")
    if playwright_path is None:
        missing.append(_missing_playwright_message())
    else:
        chromium_ready = False
        chromium_error: Optional[str] = None

        try:
            completed = subprocess.run(
                [playwright_path, "install", "--list"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            chromium_error = _missing_playwright_message()
        except Exception as exc:  # pragma: no cover - defensive guard
            chromium_error = f"Chromium runtime check failed: {exc}"
        else:
            listing = (completed.stdout or "") + (completed.stderr or "")
            chromium_lines = [line.strip() for line in listing.splitlines() if "chromium" in line.lower()]
            for raw_line in chromium_lines:
                normalized = raw_line.lower()
                if "installed" in normalized:
                    chromium_ready = True
                    break
                if raw_line.startswith("/") and Path(raw_line).exists():
                    chromium_ready = True
                    break
            if not chromium_lines:
                chromium_error = "Could not verify Chromium availability via 'playwright install --list'."

        if not chromium_ready:
            missing.append(
                chromium_error
                or "Chromium runtime missing. Run 'playwright install --with-deps chromium' and retry."
            )

    if missing:
        bullet_list = "\n".join(f"- {item}" for item in missing)
        raise DependencyError(f"Missing dependencies:\n{bullet_list}")

    global _PLAYWRIGHT_OK
    if not _PLAYWRIGHT_OK:
        _probe_chromium_launch(playwright_path=playwright_path, headless=headless)
        _PLAYWRIGHT_OK = True


def check_optional_dependencies(*, wants_wappalyzer: bool) -> None:
    """Smoke-check optional dependencies and raise DependencyError if requested but missing."""

    if not wants_wappalyzer:
        return

    global _WAPPALYZER_OK
    if _WAPPALYZER_OK:
        return

    try:
        import wappalyzer  # noqa: F401
    except ImportError as exc:  # pragma: no cover - runtime guard
        raise DependencyError(_missing_wappalyzer_message()) from exc

    firefox_path = which("firefox") or which("firefox-esr")
    geckodriver_path = which("geckodriver")

    missing_messages: list[str] = []
    if not firefox_path:
        missing_messages.append(
            "Firefox browser required for Wappalyzer. Install via your package manager."
        )
    if not geckodriver_path:
        missing_messages.append(
            "Geckodriver binary required for Wappalyzer. Install from https://github.com/mozilla/geckodriver/releases."
        )

    if missing_messages:
        bullet_list = "\n".join(f"- {msg}" for msg in missing_messages)
        raise DependencyError(f"Missing Wappalyzer dependencies:\n{bullet_list}")

    # Optional: verify geckodriver is runnable
    try:
        subprocess.run(
            [geckodriver_path, "--version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise DependencyError(
            f"Geckodriver is not runnable: {exc}. Ensure it is executable and on PATH."
        ) from exc

    _WAPPALYZER_OK = True
