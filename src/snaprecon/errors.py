"""Custom exceptions for SnapRecon."""

from typing import Optional


class SnapReconError(Exception):
    """Base exception for SnapRecon."""
    
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.details = details


class ScopeError(SnapReconError):
    """Raised when scope validation fails."""
    pass


class CostExceeded(SnapReconError):
    """Raised when cost limits would be exceeded."""
    pass


class NavigationError(SnapReconError):
    """Raised when browser navigation fails."""
    pass


class LLMError(SnapReconError):
    """Raised when Gemini API calls fail."""
    pass


class ConfigurationError(SnapReconError):
    """Raised when configuration is invalid."""
    pass


class DiscoveryError(SnapReconError):
    """Raised when subdomain discovery fails."""
    pass


class DependencyError(SnapReconError):
    """Raised when required external dependencies are unavailable."""
    pass
