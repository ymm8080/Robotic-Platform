"""Message Gateway - Main FastAPI application.

Endpoints:
- GET  /health                         - Health check
- POST /api/v1/notifications/send       - Send notification to channels
- POST /webhook/{platform}              - Unified platform callback (wechat/feishu/dingtalk)
- GET  /api/v1/operations/{id}          - Query operation status
- GET  /api/v1/audit/logs               - Query audit logs
"""

import json
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, Query, Request

from .action_validator import ActionValidator
from .audit_logger import AuditLogger
from .card_template_engine import CardTemplateEngine
from .config import settings
from .email_gateway import EmailGateway
from .message_router import MessageRouter
from .models import (
    ActionType,
    CallbackResponse,
    NotificationRequest,
    NotificationResponse,
    OperationStatus,
    utc_now_iso,
)
from .platform_adapters import DingTalkAdapter, FeishuAdapter, WeChatAdapter

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("gateway")

# Global components
router = MessageRouter()
card_engine = CardTemplateEngine()
validator = ActionValidator()
audit = AuditLogger()
email_gw = EmailGateway()
wechat = WeChatAdapter()
feishu = FeishuAdapter()
dingtalk = DingTalkAdapter()

# Redis for operation state
_redis: aioredis.Redis | None = None
_http: httpx.AsyncClient | None = None


def _require_gateway_api_key(provided: str | None) -> None:
    """Raise 401 if the provided key does not match the configured key."""
    configured = settings.gateway_api_key
    if not configured:
        return
    if not provided or not secrets.compare_digest(configured, provided):
        logger.warning("Gateway API key auth failed")
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global _redis, _http
    logger.info("[Gateway] Starting message gateway v3.5...")

    # Security: refuse to start in production without API key (skip in tests)
    _is_test = "pytest" in sys.modules
    if (
        not _is_test
        and os.getenv("MODE", "PRODUCTION").upper() == "PRODUCTION"
        and not settings.gateway_api_key
    ):
        raise RuntimeError("FATAL: GATEWAY_API_KEY is not configured in PRODUCTION mode.")

    # Initialize all components
    await router.init()
    await validator.init()
    await audit.init()
    await wechat.init()
    await feishu.init()
    await dingtalk.init()

    redis_kwargs = {"decode_responses": True}
    if (
        settings.REDIS_URL.startswith("rediss://")
        or os.getenv("REDIS_SSL", "false").lower() == "true"
    ):
        redis_kwargs["ssl"] = True
        redis_kwargs["ssl_cert_reqs"] = os.getenv("REDIS_SSL_CERT_REQS", "required")
    _redis = aioredis.from_url(settings.REDIS_URL, **redis_kwargs)
    _http = httpx.AsyncClient(timeout=10.0)

    logger.info(
        "[Gateway] All components initialized. Enabled channels: %s", settings.enabled_channels
    )
    yield

    # Shutdown
    logger.info("[Gateway] Shutting down...")
    await router.close()
    await validator.close()
    await audit.close()
    await wechat.close()
    await feishu.close()
    await dingtalk.close()
    if _redis:
        await _redis.close()
    if _http:
        await _http.aclose()
    logger.info("[Gateway] Shutdown complete.")


app = FastAPI(
    title="SAP-EWM Message Gateway",
    description="Multi-channel notification gateway with six-layer accuracy validation",
    version="3.5.0",
    lifespan=lifespan,
)


# -- Health Check --


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.5.0",
        "channels": settings.enabled_channels,
        "audit": audit.status,
        "timestamp": utc_now_iso(),
    }


# -- Send Notification --


@app.post("/api/v1/notifications/send", response_model=NotificationResponse)
async def send_notification(
    req: NotificationRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Send a notification to specified channels.

    System → Gateway: Core platform sends alert via this endpoint.
    Gateway routes to WeChat/Feishu/DingTalk/Email based on priority and config.
    """
    _require_gateway_api_key(x_api_key)
    logger.info(
        "[Gateway] Notification received: alert_id=%s, priority=%s, action=%s",
        req.alert_id,
        req.priority,
        req.action_type,
    )

    # 1. Route message
    route_result = await router.route(req)

    if route_result.get("skipped"):
        return NotificationResponse(
            code=0,
            message=f"告警已跳过: {route_result.get('reason', 'unknown')}",
            data={"notification_id": f"NOTI_{uuid4().hex[:12]}", "channel_results": []},
        )

    channels = route_result["channels"]
    notification_id = f"NOTI_{uuid4().hex[:12]}"
    channel_results = []

    # 2. Generate platform-specific cards
    wechat_card = card_engine.generate_wechat_card(req)
    feishu_card = card_engine.generate_feishu_card(req)
    dingtalk_card = card_engine.generate_dingtalk_card(req)
    email_subject, email_html = card_engine.generate_email_body(req)

    # 3. Send to each channel
    for channel in channels:
        try:
            if channel == "wechat":
                result = await wechat.send_message(wechat_card, req.recipients)
            elif channel == "feishu":
                result = await feishu.send_message(feishu_card, req.recipients)
            elif channel == "dingtalk":
                result = await dingtalk.send_message(dingtalk_card, req.recipients)
            elif channel == "email":
                result = await email_gw.send(req, req.recipients, email_subject, email_html)
            else:
                result = {
                    "status": "skipped",
                    "message_id": None,
                    "error": f"unknown channel: {channel}",
                }

            channel_results.append(
                {
                    "channel": channel,
                    "status": result.get("status", "unknown"),
                    "message_id": result.get("message_id"),
                    "error": result.get("error"),
                }
            )
        except Exception as e:
            logger.error("[Gateway] Channel %s error: %s", channel, e)
            channel_results.append(
                {
                    "channel": channel,
                    "status": "failed",
                    "message_id": None,
                    "error": str(e),
                }
            )

    # 4. Create operation record in Redis
    execution_id = f"EXEC_{uuid4().hex[:12]}"
    op_data = {
        "execution_id": execution_id,
        "notification_id": notification_id,
        "status": OperationStatus.NOTIFIED.value,
        "action_type": req.action_type.value,
        "target_id": req.target.target_id,
        "target_type": req.target.target_type.value,
        "alert_id": req.alert_id,
        "correlation_id": req.correlation_id,
        "created_at": utc_now_iso(),
        "require_confirm": str(req.require_confirm).lower(),
    }
    await _redis.hset(f"gateway:op:{execution_id}", mapping=op_data)
    await _redis.expire(f"gateway:op:{execution_id}", 86400)  # 24h TTL

    # 5. Audit log
    await audit.log(
        operator="system",
        operator_name="Core Platform",
        platform="internal",
        action_type=req.action_type.value,
        target_id=req.target.target_id,
        target_type=req.target.target_type.value,
        status=OperationStatus.NOTIFIED.value,
        execution_id=execution_id,
        detail={
            "notification_id": notification_id,
            "channels": channels,
            "channel_results": channel_results,
            "alert_id": req.alert_id,
        },
        is_critical=req.priority == "P0",
        correlation_id=req.correlation_id,
    )

    return NotificationResponse(
        code=0,
        message="发送成功",
        data={
            "notification_id": notification_id,
            "execution_id": execution_id,
            "channel_results": channel_results,
        },
    )


# -- Platform Callback (Unified) --


@app.post("/webhook/{platform}")
async def platform_callback(
    platform: str,
    request: Request,
):
    """Unified platform callback endpoint.

    Platforms (wechat/feishu/dingtalk) call this when user clicks a button.
    All callbacks must pass signature verification before processing.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        logger.warning("[Gateway] Invalid JSON in callback body")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 1. Handle Feishu URL verification challenge
    if platform == "feishu":
        challenge = feishu.verify_challenge(body)
        if challenge:
            return challenge

    # 2. Verify platform signature
    if platform == "wechat":
        signature = request.query_params.get("msg_signature", "")
        timestamp = request.query_params.get("timestamp", "")
        nonce = request.query_params.get("nonce", "")
        if not wechat.verify_signature(signature, timestamp, nonce):
            logger.warning("[Gateway] WeChat signature verification failed")
            raise HTTPException(status_code=403, detail="Signature verification failed")

    elif platform == "feishu":
        token = body.get("token", "")
        if not feishu.verify_token(token):
            logger.warning("[Gateway] Feishu token verification failed")
            raise HTTPException(status_code=403, detail="Token verification failed")

    elif platform == "dingtalk":
        timestamp = request.query_params.get("timestamp", "")
        sign = request.query_params.get("sign", "")
        if not dingtalk.verify_sign(timestamp, sign):
            logger.warning("[Gateway] DingTalk signature verification failed")
            raise HTTPException(status_code=403, detail="Signature verification failed")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

    # 3. Parse callback into unified format
    if platform == "wechat":
        callback = wechat.parse_callback(body)
    elif platform == "feishu":
        callback = feishu.parse_callback(body)
    elif platform == "dingtalk":
        callback = dingtalk.parse_callback(body)
    else:
        callback = None

    if not callback:
        logger.error("[Gateway] Failed to parse callback from %s", platform)
        raise HTTPException(status_code=400, detail="Failed to parse callback")

    logger.info(
        "[Gateway] Callback received: platform=%s, user=%s, action=%s, target=%s",
        platform,
        callback.user.platform_user_id,
        callback.action.action_type,
        callback.action.target_id,
    )

    # 4. Check if this is a dismiss/view action (no validation needed)
    if callback.action.action_type in (
        ActionType.DISMISS,
        ActionType.VIEW_ORDER,
        ActionType.VIEW_ROBOT,
    ):
        await audit.log(
            operator=callback.user.bound_user_id or callback.user.platform_user_id,
            operator_name=callback.user.platform_user_name,
            platform=platform,
            action_type=callback.action.action_type.value,
            target_id=callback.action.target_id,
            target_type=callback.action.target_type.value,
            status=OperationStatus.SUCCESS.value,
            detail={"event_id": callback.event_id},
            is_critical=False,
            correlation_id=callback.card_context.correlation_id,
        )
        return CallbackResponse(
            code=0,
            message="操作已处理",
            data={"execution_id": "", "status": "success"},
        )

    # 5. Run six-layer validation
    confirm_token = callback.action.params.get("confirm_token")
    results = await validator.validate(
        platform=platform,
        platform_user_id=callback.user.platform_user_id,
        action=callback.action,
        card_context=callback.card_context.model_dump(),
        confirm_token=confirm_token,
    )

    # Check if any layer failed
    failed = [r for r in results if not r.passed]

    if failed:
        first_fail = failed[0]

        # Check if it's a secondary confirmation request (not a real failure)
        if first_fail.layer == "secondary_confirm" and first_fail.detail.get("need_confirm"):
            # Generate and send secondary confirmation card
            token = first_fail.detail["confirm_token"]
            execution_id = f"EXEC_{uuid4().hex[:12]}"

            # Send secondary confirmation card to the same channel
            confirm_card = card_engine.generate_secondary_confirm_card(
                platform=platform,
                action_type=callback.action.action_type,
                target_id=callback.action.target_id,
                target_type=callback.action.target_type,
                confirm_token=token,
                alert_id=callback.card_context.original_alert_id,
            )

            if platform == "wechat":
                await wechat.send_message(confirm_card, [callback.user.platform_user_id])
            elif platform == "feishu":
                await feishu.send_message(confirm_card, [callback.user.platform_user_id])
            elif platform == "dingtalk":
                await dingtalk.send_message(confirm_card, [callback.user.platform_user_id])

            # Audit log
            await audit.log(
                operator=callback.user.bound_user_id or callback.user.platform_user_id,
                operator_name=callback.user.platform_user_name,
                platform=platform,
                action_type=callback.action.action_type.value,
                target_id=callback.action.target_id,
                target_type=callback.action.target_type.value,
                status=OperationStatus.CONFIRMING.value,
                execution_id=execution_id,
                detail={"layer": "secondary_confirm", "token_issued": True},
                is_critical=True,
                correlation_id=callback.card_context.correlation_id,
            )

            return CallbackResponse(
                code=0,
                message="需要二次确认，已发送确认卡片",
                data={
                    "execution_id": execution_id,
                    "status": "confirming",
                    "confirm_token": token,
                    "confirm_expire": settings.CONFIRM_TIMEOUT_SECONDS,
                },
            )

        # Real validation failure - reject
        logger.warning(
            "[Gateway] Validation failed at layer=%s: %s",
            first_fail.layer,
            first_fail.message,
        )

        await audit.log(
            operator=callback.user.bound_user_id or callback.user.platform_user_id,
            operator_name=callback.user.platform_user_name,
            platform=platform,
            action_type=callback.action.action_type.value,
            target_id=callback.action.target_id,
            target_type=callback.action.target_type.value,
            status=OperationStatus.FAILED.value,
            detail={
                "failed_layer": first_fail.layer,
                "failure_message": first_fail.message,
                "all_results": [{"layer": r.layer, "passed": r.passed} for r in results],
            },
            is_critical=True,
            correlation_id=callback.card_context.correlation_id,
        )

        return CallbackResponse(
            code=403,
            message=f"操作被拒绝: {first_fail.message}",
            data={
                "failed_layer": first_fail.layer,
                "status": "rejected",
            },
        )

    # 6. All validation passed - execute the operation
    execution_id = f"EXEC_{uuid4().hex[:12]}"
    bound_user_id = results[0].detail.get("bound_user_id", callback.user.platform_user_id)

    # Update operation status
    op_data = {
        "execution_id": execution_id,
        "status": OperationStatus.EXECUTING.value,
        "action_type": callback.action.action_type.value,
        "target_id": callback.action.target_id,
        "target_type": callback.action.target_type.value,
        "operator": bound_user_id,
        "operator_name": callback.user.platform_user_name,
        "platform": platform,
        "created_at": utc_now_iso(),
        "confirmed_at": utc_now_iso(),
    }
    await _redis.hset(f"gateway:op:{execution_id}", mapping=op_data)
    await _redis.expire(f"gateway:op:{execution_id}", 86400)

    # 7. Call core platform API to execute the action
    headers = {"Content-Type": "application/json"}
    if settings.core_platform_api_key:
        headers["X-API-Key"] = settings.core_platform_api_key
    try:
        core_resp = await _http.post(
            f"{settings.CORE_PLATFORM_URL}/api/execute",
            json={
                "execution_id": execution_id,
                "action_type": callback.action.action_type.value,
                "target_id": callback.action.target_id,
                "target_type": callback.action.target_type.value,
                "operator": bound_user_id,
                "params": callback.action.params,
                "correlation_id": callback.card_context.correlation_id,
            },
            headers=headers,
        )
        if core_resp.status_code == 200:
            try:
                core_data = core_resp.json()
            except json.JSONDecodeError:
                logger.error("[Gateway] Core platform returned non-JSON 200 response")
                final_status = OperationStatus.FAILED.value
                result_data = {"error": "core_platform_non_json_response"}
            else:
                success = core_data.get("success", False)
                if success:
                    final_status = OperationStatus.SUCCESS.value
                    result_data = core_data.get("result", {})
                else:
                    final_status = OperationStatus.FAILED.value
                    result_data = {"error": core_data.get("error", "Unknown error")}
        else:
            final_status = OperationStatus.FAILED.value
            try:
                error_text = core_resp.text
            except Exception:
                error_text = f"HTTP {core_resp.status_code}"
            result_data = {"error": f"HTTP {core_resp.status_code}: {error_text[:200]}"}
    except httpx.RequestError as e:
        logger.error("[Gateway] Core platform call failed: %s", e)
        final_status = OperationStatus.FAILED.value
        result_data = {"error": str(e)}

    # 8. Update operation status
    await _redis.hset(
        f"gateway:op:{execution_id}",
        mapping={
            "status": final_status,
            "executed_at": utc_now_iso(),
            "result": json.dumps(result_data),
        },
    )

    # 9. Audit log
    await audit.log(
        operator=bound_user_id,
        operator_name=callback.user.platform_user_name,
        platform=platform,
        action_type=callback.action.action_type.value,
        target_id=callback.action.target_id,
        target_type=callback.action.target_type.value,
        status=final_status,
        execution_id=execution_id,
        detail=result_data,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
        is_critical=True,
        correlation_id=callback.card_context.correlation_id,
    )

    return CallbackResponse(
        code=0,
        message="操作已受理" if final_status == OperationStatus.SUCCESS.value else "操作执行失败",
        data={
            "execution_id": execution_id,
            "status": final_status.lower(),
            "result": result_data,
        },
    )


# -- Query Operation Status --


@app.get("/api/v1/operations/{execution_id}")
async def get_operation(
    execution_id: str,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Query the status of an operation by execution_id."""
    _require_gateway_api_key(x_api_key)
    key = f"gateway:op:{execution_id}"
    data = await _redis.hgetall(key)

    if not data:
        raise HTTPException(status_code=404, detail="Operation not found")

    return {
        "code": 0,
        "data": {
            "execution_id": execution_id,
            "status": data.get("status", "UNKNOWN"),
            "action_type": data.get("action_type", ""),
            "target_id": data.get("target_id", ""),
            "target_type": data.get("target_type", ""),
            "operator": data.get("operator", ""),
            "operator_name": data.get("operator_name", ""),
            "platform": data.get("platform", ""),
            "created_at": data.get("created_at", ""),
            "confirmed_at": data.get("confirmed_at", ""),
            "executed_at": data.get("executed_at", ""),
            "result": json.loads(data.get("result", "{}")) if data.get("result") else None,
        },
    }


# -- Query Audit Logs --


@app.get("/api/v1/audit/logs")
async def query_audit_logs(
    start_time: str = Query("", description="Start time ISO format"),
    end_time: str = Query("", description="End time ISO format"),
    user_id: str = Query("", description="Filter by user ID"),
    action_type: str = Query("", description="Filter by action type"),
    target_id: str = Query("", description="Filter by target ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Query audit logs with filters."""
    _require_gateway_api_key(x_api_key)
    result = await audit.query_logs(
        start_time=start_time,
        end_time=end_time,
        user_id=user_id,
        action_type=action_type,
        target_id=target_id,
        page=page,
        page_size=page_size,
    )
    return {"code": 0, "data": result}
