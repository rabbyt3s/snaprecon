"""Cost management and estimation for Gemini API usage."""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CostManager:
    """Manages cost tracking and estimation for Gemini API calls."""
    
    # Pricing per 1K tokens (as of 2024)
    PRICING = {
        "gemini-1.5-flash": {
            "input": 0.075,      # $0.075 per 1K input tokens
            "output": 0.30,      # $0.30 per 1K output tokens
            "vision_input": 0.15  # $0.15 per 1K vision input tokens
        },
        "gemini-1.5-pro": {
            "input": 0.375,      # $0.375 per 1K input tokens
            "output": 1.50,      # $1.50 per 1K output tokens
            "vision_input": 0.75  # $0.75 per 1K vision input tokens
        },
        "gemini-2.0-flash": {
            "input": 0.075,      # $0.075 per 1K input tokens
            "output": 0.30,      # $0.30 per 1K output tokens
            "vision_input": 0.15  # $0.15 per 1K vision input tokens
        }
    }
    
    def __init__(self, model: str = "gemini-1.5-flash"):
        self.model = model
        self.total_cost = 0.0
        self.estimates = []
        
        if model not in self.PRICING:
            logger.warning(f"Unknown model {model}, using gemini-1.5-flash pricing")
            self.model = "gemini-1.5-flash"
    
    def estimate_image_analysis_cost(self, image_size_bytes: int) -> float:
        """Estimate cost for analyzing an image."""
        # Rough estimation based on image size and model
        # Assume 1K tokens for small images, 2K for larger ones
        pricing = self.PRICING[self.model]
        
        if image_size_bytes < 100000:  # < 100KB
            estimated_tokens = 1000
        elif image_size_bytes < 500000:  # < 500KB
            estimated_tokens = 1500
        else:  # >= 500KB
            estimated_tokens = 2000
        
        # Vision input cost + estimated output cost
        input_cost = (estimated_tokens * pricing["vision_input"]) / 1000
        output_cost = (estimated_tokens * 0.5 * pricing["output"]) / 1000  # Assume 50% output tokens
        
        total_estimate = input_cost + output_cost
        
        # Store estimate for tracking
        self.estimates.append({
            "type": "image_analysis",
            "image_size": image_size_bytes,
            "estimated_tokens": estimated_tokens,
            "estimated_cost": total_estimate
        })
        
        return total_estimate
    
    def estimate_batch_cost(self, image_sizes: list[int]) -> float:
        """Estimate total cost for a batch of images."""
        total_estimate = 0.0
        
        for size in image_sizes:
            total_estimate += self.estimate_image_analysis_cost(size)
        
        return total_estimate
    
    def add_actual_cost(self, cost: float):
        """Add actual cost from completed API call."""
        self.total_cost += cost
        logger.debug(f"Added actual cost: ${cost:.4f}, total: ${self.total_cost:.4f}")
    
    def get_total_cost(self) -> float:
        """Get total actual cost incurred."""
        return self.total_cost
    
    def get_total_estimated_cost(self) -> float:
        """Get total estimated cost for all operations."""
        return sum(estimate["estimated_cost"] for estimate in self.estimates)
    
    def get_cost_accuracy(self) -> Optional[float]:
        """Get accuracy of cost estimates vs actual costs."""
        if self.total_cost == 0:
            return None
        
        estimated = self.get_total_estimated_cost()
        if estimated == 0:
            return None
        
        accuracy = (estimated - self.total_cost) / estimated
        return accuracy
    
    def check_budget_limit(self, limit: float) -> bool:
        """Check if current cost is within budget limit."""
        return self.total_cost <= limit
    
    def get_remaining_budget(self, limit: float) -> float:
        """Get remaining budget."""
        return max(0, limit - self.total_cost)
    
    def get_cost_summary(self) -> Dict:
        """Get comprehensive cost summary."""
        return {
            "model": self.model,
            "total_actual_cost": self.total_cost,
            "total_estimated_cost": self.get_total_estimated_cost(),
            "cost_accuracy": self.get_cost_accuracy(),
            "estimate_count": len(self.estimates),
            "pricing_info": self.PRICING[self.model]
        }


def format_cost(cost: float) -> str:
    """Format cost for display."""
    if cost < 0.01:
        return f"${cost:.6f}"
    elif cost < 1.0:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def estimate_run_cost(target_count: int, model: str = "gemini-1.5-flash") -> float:
    """Quick estimate for a full run."""
    cost_manager = CostManager(model)
    
    # Assume average image size of 200KB
    avg_image_size = 200000
    per_image_cost = cost_manager.estimate_image_analysis_cost(avg_image_size)
    
    return per_image_cost * target_count
