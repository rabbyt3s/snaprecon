"""SnapRecon: Authorized reconnaissance tool with screenshot analysis via Gemini Vision."""

__version__ = "0.1.0"
__author__ = "SnapRecon Team"

# Import models only - avoid circular imports
from .models import RunResult, Target, LLMResult, Error, Metadata, SafeConfig

__all__ = ["RunResult", "Target", "LLMResult", "Error", "Metadata", "SafeConfig"]
