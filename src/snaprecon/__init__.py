"""SnapRecon: Authorized reconnaissance tool with screenshot screenshots and local analysis."""

__version__ = "0.1.0"
__author__ = "SnapRecon Team"

# Import models only - avoid circular imports
from .models import RunResult, Target, AnalysisResult, Error, Metadata, SafeConfig

__all__ = ["RunResult", "Target", "AnalysisResult", "Error", "Metadata", "SafeConfig"]
