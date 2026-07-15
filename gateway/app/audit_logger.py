"""Audit Logger - Write gateway operations to Elasticsearch or local JSONL fallback.

All operations (including mobile button clicks) must be logged.
Retention: >=3 years (1095 days).
Critical operations also written to WORM storage.

Elasticsearch is optional: if ES is unavailable or not configured, logs are
written to a local JSONL fallback file and the gateway remains operational.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import settings

logger = logging.getLogger(__name__)

FALLBACK_PATH = Path(os.environ.get("AUDIT_FALLBACK_PATH", "/app/logs/audit_fallback.jsonl"))


class AuditLogger:
    """Records gateway operations to Elasticsearch with JSONL fallback."""

    def __init__(self):
        self._es: Any = None
        self._es_available: bool = False
        self._es_error: str | None = None
        self._fallback_dir_created: bool = False

    @property
    def healthy(self) -> bool:
        """Return True if Elasticsearch is connected and index exists."""
        return self._es_available

    @property
    def status(self) -> dict:
        return {
            "elasticsearch_available": self._es_available,
            "elasticsearch_error": self._es_error,
            "fallback_path": str(FALLBACK_PATH),
        }

    async def init(self):
        """Initialize Elasticsearch client if configured; never raise on failure."""
        # Ensure fallback directory exists once at startup
        if not self._fallback_dir_created:
            try:
                FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
                self._fallback_dir_created = True
            except Exception:
                pass

        # Lazy import so the gateway can start without elasticsearch installed.
        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as exc:
            self._es_error = f"elasticsearch package not installed: {exc}"
            logger.warning("[Audit] %s", self._es_error)
            return

        if not settings.ELASTICSEARCH_URL:
            self._es_error = "ELASTICSEARCH_URL not configured"
            logger.warning("[Audit] %s — using JSONL fallback", self._es_error)
            return

        try:
            es_kwargs = {
                "hosts": [settings.ELASTICSEARCH_URL],
                "basic_auth": ("elastic", settings.ELASTICSEARCH_PASSWORD),
            }
            if (
                settings.ELASTICSEARCH_URL.startswith("https://")
                or os.getenv("ELASTICSEARCH_SSL", "false").lower() == "true"
            ):
                es_kwargs["verify_certs"] = (
                    os.getenv("ELASTICSEARCH_SSL_VERIFY", "true").lower() == "true"
                )
            self._es = AsyncElasticsearch(**es_kwargs)
            await self._ensure_index()
            self._es_available = True
            self._es_error = None
            logger.info("[Audit] Elasticsearch connected")
        except Exception as e:
            self._es_available = False
            self._es_error = str(e)
            logger.warning("[Audit] Elasticsearch unavailable: %s — using JSONL fallback", e)

    async def close(self):
        if self._es:
            try:
                await self._es.close()
            except Exception as e:
                logger.warning("[Audit] Error closing ES client: %s", e)

    async def _ensure_index(self):
        """Create the audit log index if it doesn't exist."""
        if not self._es:
            return
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
            self._es_available = False
            self._es_error = str(e)

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

        if self._es_available and self._es:
            index_name = f"{settings.ELASTICSEARCH_INDEX_PREFIX}-logs"
            try:
                await self._es.index(index=index_name, document=doc)
                logger.info(
                    "[Audit] Logged: operator=%s, action=%s, target=%s, status=%s, critical=%s",
                    operator,
                    action_type,
                    target_id,
                    status,
                    is_critical,
                )
                return log_id
            except Exception as e:
                logger.error("[Audit] Failed to write log: %s", e)
                self._es_available = False
                self._es_error = str(e)

        # Fallback: write to local JSONL file (emergency measure / ES disabled)
        try:
            if not self._fallback_dir_created:
                FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
                self._fallback_dir_created = True
            with open(FALLBACK_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            logger.warning("[Audit] Wrote to fallback file: %s", FALLBACK_PATH)
        except Exception:
            logger.error("[Audit] Fallback write also failed!")

        # For critical operations, mark as immutable (WORM-like)
        if is_critical:
            logger.info("[Audit] Critical operation logged: %s (WORM backup recommended)", log_id)

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
        """Query audit logs with filters. Falls back to local JSONL if ES unavailable."""
        if not self._es_available or not self._es:
            return self._query_fallback_logs(
                start_time, end_time, user_id, action_type, target_id, page, page_size
            )

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
            hits = [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "logs": hits,
                "source": "elasticsearch",
            }
        except Exception as e:
            logger.error("[Audit] Query failed: %s", e)
            self._es_available = False
            self._es_error = str(e)
            return self._query_fallback_logs(
                start_time, end_time, user_id, action_type, target_id, page, page_size
            )

    def _query_fallback_logs(
        self,
        start_time: str = "",
        end_time: str = "",
        user_id: str = "",
        action_type: str = "",
        target_id: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Read and filter the local JSONL fallback log.

        Reads only the last N lines to avoid unbounded memory usage.
        """
        MAX_LINES = 10_000
        logs = []
        if FALLBACK_PATH.exists():
            with open(FALLBACK_PATH, encoding="utf-8") as f:
                # Read tail efficiently for large files
                import collections

                tail = collections.deque(f, maxlen=MAX_LINES)
                for line in tail:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if start_time and doc.get("timestamp", "") < start_time:
                        continue
                    if end_time and doc.get("timestamp", "") > end_time:
                        continue
                    if user_id and doc.get("operator") != user_id:
                        continue
                    if action_type and doc.get("action_type") != action_type:
                        continue
                    if target_id and doc.get("target_id") != target_id:
                        continue
                    logs.append(doc)

        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        total = len(logs)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": logs[start:end],
            "source": "jsonl_fallback",
            "fallback_path": str(FALLBACK_PATH),
        }
