"""Safety and scope validation for SnapRecon."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Set

from .errors import ScopeError
from .models import Target

logger = logging.getLogger(__name__)


def load_scope_file(scope_file: Path) -> Set[str]:
    """Load allowed domains and suffixes from scope file."""
    try:
        with open(scope_file, "r") as f:
            lines = f.readlines()
        
        allowed = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                allowed.add(line.lower())
        
        return allowed
    
    except FileNotFoundError:
        raise ScopeError(
            f"Scope file not found: {scope_file}",
            code="SCOPE_FILE_MISSING"
        )
    except Exception as e:
        raise ScopeError(
            f"Error reading scope file: {e}",
            code="SCOPE_FILE_ERROR"
        )


def is_in_scope(host: str, allowed_domains: Set[str]) -> bool:
    """Check if a host is within the allowed scope."""
    host_lower = host.lower()
    
    for allowed in allowed_domains:
        # Exact match
        if host_lower == allowed:
            return True
        
        # Suffix match (e.g., "example.com" matches "sub.example.com")
        if allowed.startswith("."):
            if host_lower.endswith(allowed):
                return True
        else:
            if host_lower == allowed or host_lower.endswith(f".{allowed}"):
                return True
    
    return False


def enforce_scope(targets: List[Target], scope_file: str) -> List[Target]:
    """Filter targets to only include those within scope."""
    scope_path = Path(scope_file)
    if not scope_path.exists():
        raise ScopeError(
            f"Scope file does not exist: {scope_file}",
            code="SCOPE_FILE_NOT_FOUND"
        )
    
    allowed_domains = load_scope_file(scope_path)
    logger.info(f"Loaded {len(allowed_domains)} allowed domains/suffixes from scope file")
    
    if not allowed_domains:
        raise ScopeError(
            "Scope file is empty or contains no valid entries",
            code="SCOPE_FILE_EMPTY"
        )
    
    # Filter targets
    in_scope = []
    out_of_scope = []
    
    for target in targets:
        if is_in_scope(target.host, allowed_domains):
            in_scope.append(target)
        else:
            out_of_scope.append(target)
            logger.warning(f"Target {target.host} is out of scope")
    
    logger.info(f"Scope filtering: {len(in_scope)} in scope, {len(out_of_scope)} out of scope")
    
    if not in_scope:
        raise ScopeError(
            "No targets remain after scope filtering",
            code="NO_TARGETS_IN_SCOPE"
        )
    
    return in_scope


def check_denylist(targets: List[Target], denylist_file: Optional[Path] = None) -> List[Target]:
    """Check targets against denylist and remove blocked ones."""
    if not denylist_file or not denylist_file.exists():
        return targets
    
    try:
        with open(denylist_file, "r") as f:
            lines = f.readlines()
        
        blocked = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                blocked.add(line.lower())
        
        if not blocked:
            return targets
        
        # Filter out blocked targets
        allowed = []
        blocked_count = 0
        
        for target in targets:
            if target.host.lower() not in blocked:
                allowed.append(target)
            else:
                blocked_count += 1
                logger.warning(f"Target {target.host} is in denylist")
        
        logger.info(f"Denylist filtering: {len(allowed)} allowed, {blocked_count} blocked")
        return allowed
        
    except Exception as e:
        logger.warning(f"Error reading denylist file: {e}")
        return targets


def validate_scope_file(scope_file: str) -> bool:
    """Validate that scope file exists and is readable."""
    scope_path = Path(scope_file)
    
    if not scope_path.exists():
        raise ScopeError(
            f"Scope file does not exist: {scope_file}",
            code="SCOPE_FILE_NOT_FOUND"
        )
    
    if not scope_path.is_file():
        raise ScopeError(
            f"Scope file is not a regular file: {scope_file}",
            code="SCOPE_FILE_INVALID"
        )
    
    if not scope_path.stat().st_size > 0:
        raise ScopeError(
            f"Scope file is empty: {scope_file}",
            code="SCOPE_FILE_EMPTY"
        )
    
    return True
