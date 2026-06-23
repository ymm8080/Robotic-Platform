"""
Brand strategy registry — loads and manages robot brand strategies.
Strategies are registered by brand name and can be looked up at runtime.
"""
import logging
from typing import Optional

from .base import BaseStrategy
from .kuka import KukaStrategy
from .mir import MirStrategy
from .otto import OttoStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry of robot brand strategies.

    Strategies can be:
    - Pre-registered (built-in brands)
    - Loaded from config (future: plugin-based)
    - Injected at runtime (for testing)
    """

    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}
        self._register_builtin()

    def _register_builtin(self):
        """Register all built-in brand strategies."""
        for strategy in [KukaStrategy(), MirStrategy(), OttoStrategy()]:
            self._strategies[strategy.brand.upper()] = strategy
            logger.info(f"Registered strategy: {strategy}")

    def register(self, strategy: BaseStrategy):
        """Register a custom strategy (for testing or plugins)."""
        key = strategy.brand.upper()
        self._strategies[key] = strategy
        logger.info(f"Registered custom strategy: {strategy}")

    def get(self, brand: str) -> Optional[BaseStrategy]:
        """Get strategy by brand name. Case-insensitive."""
        return self._strategies.get(brand.upper())

    def get_or_fallback(self, brand: str) -> BaseStrategy:
        """Get strategy or return fallback for unknown brands."""
        strategy = self.get(brand)
        if strategy is None:
            logger.warning(f"No strategy for brand '{brand}', using fallback")
            return self._fallback()
        return strategy

    def list_brands(self) -> list[str]:
        """List all registered brand names."""
        return sorted(self._strategies.keys())

    def count(self) -> int:
        """Number of registered strategies."""
        return len(self._strategies)

    def _fallback(self) -> BaseStrategy:
        """Return a generic fallback strategy for unknown brands."""
        # Fallback: use KUKA strategy as it's the most standard VDA5050
        return self._strategies.get("KUKA", KukaStrategy())

    def __repr__(self) -> str:
        brands = ", ".join(self.list_brands())
        return f"<StrategyRegistry brands=[{brands}]>"


# Module-level singleton for easy import
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry singleton."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry
