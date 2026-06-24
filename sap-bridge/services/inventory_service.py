"""
Inventory sync service — pulls stock data from SAP EWM and caches in Redis.
References:
  REFERENCE/05_reference/sap/odata-warehouse-task-api.md
"""
import json
import logging
import os
import time

import redis as rd

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
INVENTORY_TTL = 300  # 5 min cache TTL
SYNC_INTERVAL = 300  # 5 min between full syncs


class InventoryService:
    """Manages inventory cache synced from SAP EWM.

    Inventory data is cached in Redis with TTL to reduce SAP load.
    """

    def __init__(self):
        self._redis = rd.from_url(REDIS_URL, decode_responses=True)
        self._last_sync = 0.0

    def get_stock(self, product: str, warehouse: str = "WM01",
                  batch: str | None = None) -> float | None:
        """Get cached stock quantity for a product.

        Returns cached value, or None if not in cache (triggers sync).
        """
        key = f"inventory:{warehouse}:{product}"
        if batch:
            key += f":{batch}"

        data = self._redis.get(key)
        if data is not None:
            return float(data)
        return None

    def get_all_stock(self, warehouse: str = "WM01") -> dict[str, float]:
        """Get all cached inventory for a warehouse."""
        pattern = f"inventory:{warehouse}:*"
        keys = self._redis.keys(pattern)
        result = {}
        for key in keys:
            product = key.replace(f"inventory:{warehouse}:", "")
            val = self._redis.get(key)
            if val is not None:
                result[product] = float(val)
        return result

    def update_stock(self, product: str, quantity: float,
                     warehouse: str = "WM01", batch: str | None = None):
        """Update cached stock for a product."""
        key = f"inventory:{warehouse}:{product}"
        if batch:
            key += f":{batch}"
        self._redis.setex(key, INVENTORY_TTL, str(quantity))
        logger.debug(f"Updated inventory: {key} = {quantity}")

    def update_batch(self, items: list[dict], warehouse: str = "WM01"):
        """Batch update inventory cache."""
        pipe = self._redis.pipeline()
        count = 0
        for item in items:
            product = item.get("product")
            qty = float(item.get("quantity", 0))
            batch = item.get("batch")
            if not product:
                continue
            key = f"inventory:{warehouse}:{product}"
            if batch:
                key += f":{batch}"
            pipe.setex(key, INVENTORY_TTL, str(qty))
            count += 1
        pipe.execute()
        logger.info(f"Updated {count} inventory items for warehouse {warehouse}")

    def report_consumption(self, product: str, quantity: float,
                           order_id: str, warehouse: str = "WM01"):
        """Record material consumption for an order.

        Decrements cached stock and logs the event.
        """
        current = self.get_stock(product, warehouse)
        if current is not None:
            new_qty = max(0, current - quantity)
            self.update_stock(product, new_qty, warehouse)
        self._log_event("CONSUMPTION", product, quantity, order_id, warehouse)

    def report_production(self, product: str, quantity: float,
                          order_id: str, warehouse: str = "WM01"):
        """Record material production/completion for an order."""
        current = self.get_stock(product, warehouse)
        if current is not None:
            new_qty = current + quantity
            self.update_stock(product, new_qty, warehouse)
        self._log_event("PRODUCTION", product, quantity, order_id, warehouse)

    def needs_sync(self) -> bool:
        """Check if a full sync from SAP is needed."""
        return time.time() - self._last_sync > SYNC_INTERVAL

    def mark_synced(self):
        """Mark sync completed."""
        self._last_sync = time.time()
        self._redis.set("inventory:last_sync", str(self._last_sync))

    def clear_cache(self, warehouse: str = "WM01"):
        """Clear all cached inventory for a warehouse."""
        pattern = f"inventory:{warehouse}:*"
        keys = self._redis.keys(pattern)
        if keys:
            self._redis.delete(*keys)
            logger.info(f"Cleared {len(keys)} inventory cache entries for {warehouse}")

    def _log_event(self, event: str, product: str, qty: float,
                   order_id: str, warehouse: str):
        """Log inventory event to Redis for audit/alert."""
        log_key = f"inventory:events:{warehouse}"
        entry = json.dumps({
            "event": event,
            "product": product,
            "quantity": qty,
            "orderId": order_id,
            "timestamp": time.time(),
        })
        self._redis.lpush(log_key, entry)
        self._redis.ltrim(log_key, 0, 999)  # Keep last 1000 events
        self._redis.expire(log_key, 86400)   # Auto-clean after 24h
        logger.info(f"Inventory {event}: {product} qty={qty} order={order_id}")
