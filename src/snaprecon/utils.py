"""Utility functions for SnapRecon."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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
