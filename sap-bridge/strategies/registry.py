"""
Brand strategy registry — loads and manages robot brand strategies.
Strategies are registered by brand name and can be looked up at runtime.

v4.1: Added get_or_raise() for strict brand lookup (501 on unknown)
      and version compatibility verification.
"""
import logging

from .base import MIN_VDA5050_VERSION, BaseStrategy
from .geekplus import GeekPlusStrategy
from .hairobotics import HaiRoboticsStrategy
from .kuka import KukaStrategy
from .mir import MirStrategy
from .otto import OttoStrategy
from .quicktron import QuicktronStrategy

logger = logging.getLogger(__name__)


class UnknownBrandError(Exception):
    """Raised when a brand is not registered in the strategy registry.

    Maps to HTTP 501 in the API layer — the server does not support
    dispatching to this brand.
    """

    def __init__(self, brand: str, available: list[str] | None = None):
        self.brand = brand
        self.available = available or []
        avail_str = ", ".join(self.available) if self.available else "none"
        super().__init__(f"Unknown brand '{brand}'. Available: {avail_str}")


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
        for strategy in [
            KukaStrategy(), MirStrategy(), OttoStrategy(),
            GeekPlusStrategy(), HaiRoboticsStrategy(), QuicktronStrategy(),
        ]:
            self._strategies[strategy.brand.upper()] = strategy
            logger.info(f"Registered strategy: {strategy}")

    def register(self, strategy: BaseStrategy):
        """Register a custom strategy (for testing or plugins)."""
        key = strategy.brand.upper()
        self._strategies[key] = strategy
        logger.info(f"Registered custom strategy: {strategy}")

    def get(self, brand: str) -> BaseStrategy | None:
        """Get strategy by brand name. Case-insensitive."""
        return self._strategies.get(brand.upper())

    def get_or_fallback(self, brand: str) -> BaseStrategy:
        """Get strategy or return fallback for unknown brands."""
        strategy = self.get(brand)
        if strategy is None:
            logger.warning(f"No strategy for brand '{brand}', using fallback")
            return self._fallback()
        return strategy

    def get_or_raise(self, brand: str) -> BaseStrategy:
        """Get strategy by brand name. Raises UnknownBrandError if not found.

        v4.1: Strict lookup for dispatch endpoint — unknown brands must
        return 501 to the client, not silently fall back.

        Args:
            brand: Brand name (case-insensitive).

        Returns:
            The registered BaseStrategy for this brand.

        Raises:
            UnknownBrandError: If the brand is not registered.
        """
        strategy = self.get(brand)
        if strategy is None:
            raise UnknownBrandError(brand, available=self.list_brands())
        return strategy

    def verify_version(self, brand: str, min_version: str = MIN_VDA5050_VERSION) -> bool:
        """Verify that a brand's strategy supports the minimum VDA5050 version.

        v4.1 verification matrix item 3: All brands must support >= v1.1.0.

        Args:
            brand: Brand name (case-insensitive).
            min_version: Minimum required VDA5050 version.

        Returns:
            True if the strategy supports >= min_version.

        Raises:
            UnknownBrandError: If the brand is not registered.
        """
        strategy = self.get_or_raise(brand)
        compatible = strategy.check_version_compatibility(min_version)
        if not compatible:
            logger.warning(
                f"Brand '{brand}' does not support VDA5050 >= {min_version} "
                f"(supports: {strategy.supported_versions})"
            )
        return compatible

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
_registry: StrategyRegistry | None = None


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry singleton."""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry
