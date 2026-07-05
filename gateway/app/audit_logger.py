"""Audit Logger - Write all gateway operations to Elasticsearch (immutable audit trail).

All operations (including mobile button clicks) must be logged.
Retention: >=3 years (1095 days).
Critical operations also written to WORM storage.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from elasticsearch import AsyncElasticsearch

from .config import settings

logger = logging.getLogger(__name__)


class AuditLogger:
    """Records all gateway operations to Elasticsearch audit index."""

    def __init__(self):
        self._es: Optional[AsyncElasticsearch] = None

    async def init(self):
        """Initialize Elasticsearch client and ensure index exists."""
        self._es = AsyncElasticsearch(
            hosts=[settings.ELASTICSEARCH_URL],
            basic_auth=("elastic", settings.ELASTICSEARCH_PASSWORD),
        )
        await self._ensure_index()

    async def close(self):
        if self._es:
            await self._es.close()

    async def _ensure_index(self):
        """Create the audit log index if it doesn't exist."""
        index_name = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-logs"
        try:
            exists = await self._es.indices.exists(index=index_name)
            if not exists:
                mapping = {
                    "mappings": {
                        "properties": {
                            "log_id": {"type": "keyword"},
                            "timestamp": {"type": "date"},
                            "operator": {"type": "keyword"},
                            "operator_name": {"type": "keyword"},
                            "platform": {"type": "keyword"},
                            "action_type": {"type": "keyword"},
                            "target_id": {"type": "keyword"},
                            "target_type": {"type": "keyword"},
                            "execution_id": {"type": "keyword"},
                            "status": {"type": "keyword"},
                            "detail": {"type": "object", "enabled": True},
                            "ip_address": {"type": "ip"},
                            "user_agent": {"type": "text"},
                            "is_critical": {"type": "boolean"},
                            "correlation_id": {"type": "keyword"},
                        }
                    },
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "index.lifecycle.name": "gateway-audit-retention",
                    },
                }
                await self._es.indices.create(index=index_name, body=mapping)
                logger.info("[Audit] Created index: %s", index_name)
        except Exception as e:
            logger.error("[Audit] Failed to ensure index: %s", e)

    async def log(
        self,
        operator: str,
        operator_name: str,
        platform: str,
        action_type: str,
        target_id: str,
        target_type: str,
        status: str,
        execution_id: str = "",
        detail: dict = None,
        ip_address: str = "",
        user_agent: str = "",
        is_critical: bool = False,
        correlation_id: str = "",
    ) -> str:
        """Write a single audit log entry.

        Returns the log_id.
        """
        log_id = f"LOG_{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        doc = {
            "log_id": log_id,
            "timestamp": timestamp,
            "operator": operator,
            "operator_name": operator_name,
            "platform": platform,
            "action_type": action_type,
            "target_id": target_id,
            "target_type": target_type,
            "execution_id": execution_id,
            "status": status,
            "detail": detail or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "is_critical": is_critical,
            "correlation_id": correlation_id,
        }

        index_name = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-logs"
        try:
            await self._es.index(index=index_name, document=doc)
            logger.info(
                "[Audit] Logged: operator=%s, action=%s, target=%s, status=%s, critical=%s",
                operator, action_type, target_id, status, is_critical,
            )
        except Exception as e:
            logger.error("[Audit] Failed to write log: %s", e)
            # Fallback: write to local file as emergency measure
            try:
                import json
                from pathlib import Path
                fallback_path = Path("/app/logs/audit_fallback.jsonl")
                with open(fallback_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                logger.warning("[Audit] Wrote to fallback file: %s", fallback_path)
            except Exception:
                logger.error("[Audit] Fallback write also failed!")

        # For critical operations, mark as immutable (WORM-like)
        # In production, this would write to a WORM storage device
        if is_critical:
            logger.info(
                "[Audit] Critical operation logged: %s (WORM backup recommended)", log_id
            )

        return log_id

    async def query_logs(
        self,
        start_time: str = "",
        end_time: str = "",
        user_id: str = "",
        action_type: str = "",
        target_id: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Query audit logs with filters."""
        must = []
        filter_clauses = []

        if start_time:
            filter_clauses.append({"range": {"timestamp": {"gte": start_time}}})
        if end_time:
            filter_clauses.append({"range": {"timestamp": {"lte": end_time}}})
        if user_id:
            must.append({"term": {"operator": user_id}})
        if action_type:
            must.append({"term": {"action_type": action_type}})
        if target_id:
            must.append({"term": {"target_id": target_id}})

        query = {"bool": {"must": must, "filter": filter_clauses}}

        from_ = (page - 1) * page_size

        index_name = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-logs"
        try:
            result = await self._es.search(
                index=index_name,
                query=query,
                sort=[{"timestamp": {"order": "desc"}}],
                from_=from_,
                size=page_size,
            )

            total = result.get("hits", {}).get("total", {}).get("value", 0)
            hits = [
                hit["_source"]
                for hit in result.get("hits", {}).get("hits", [])
            ]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "logs": hits,
            }
        except Exception as e:
            logger.error("[Audit] Query failed: %s", e)
            return {"total": 0, "page": page, "page_size": page_size, "logs": []}
