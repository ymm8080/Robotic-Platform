"""Action Validator - Six-layer accuracy validation for mobile operations.

Six layers (all must pass, any failure = reject):
1. Identity verification - verify platform user is bound to a system user
2. Permission check - verify user has permission for the action type
3. Object validation - verify the target object exists and is in a valid state
4. Anti-replay - verify this exact operation hasn't been processed already
5. Secondary confirmation - for dangerous operations, require explicit second click
6. Pre-execution validation - verify the operation can be safely executed right now
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
import redis.asyncio as aioredis

from .config import settings
from .models import ActionType, CallbackAction, OperationStatus, TargetType

logger = logging.getLogger(__name__)

# Action types that require secondary confirmation
DANGEROUS_ACTIONS = {
    ActionType.ROBOT_STOP,
    ActionType.ORDER_CANCEL,
    ActionType.ROBOT_RECALL,
    ActionType.ZONE_LOCK,
}

# Action types that are read-only (no validation needed beyond identity)
READONLY_ACTIONS = {
    ActionType.DISMISS,
    ActionType.VIEW_ORDER,
    ActionType.VIEW_ROBOT,
}


class ValidationResult:
    """Result of a validation layer."""

    def __init__(self, passed: bool, layer: str, message: str = "", detail: dict = None):
        self.passed = passed
        self.layer = layer
        self.message = message
        self.detail = detail or {}

    def __repr__(self):
        return f"ValidationResult(passed={self.passed}, layer={self.layer}, message={self.message})"


class ActionValidator:
    """Six-layer accuracy validation for all mobile operations."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def init(self):
        """Initialize async resources."""
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self._http_client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        """Cleanup async resources."""
        if self._redis:
            await self._redis.close()
        if self._http_client:
            await self._http_client.aclose()

    async def validate(
        self,
        platform: str,
        platform_user_id: str,
        action: CallbackAction,
        card_context: dict,
        confirm_token: Optional[str] = None,
    ) -> list[ValidationResult]:
        """Run all six validation layers. Returns list of all results.

        Any failure means the operation must be rejected.
        """
        results = []

        # Layer 1: Identity verification
        r1 = await self._verify_identity(platform, platform_user_id)
        results.append(r1)
        if not r1.passed:
            return results

        bound_user_id = r1.detail.get("bound_user_id", "")

        # Layer 2: Permission check
        r2 = await self._check_permission(bound_user_id, action.action_type)
        results.append(r2)
        if not r2.passed:
            return results

        # Layer 3: Object validation
        r3 = await self._validate_object(action)
        results.append(r3)
        if not r3.passed:
            return results

        # Layer 4: Anti-replay
        r4 = await self._check_anti_replay(
            platform_user_id, action, card_context
        )
        results.append(r4)
        if not r4.passed:
            return results

        # Layer 5: Secondary confirmation
        r5 = await self._secondary_confirmation(
            action, card_context, confirm_token
        )
        results.append(r5)
        if not r5.passed:
            return results

        # Layer 6: Pre-execution validation
        r6 = await self._pre_execution_validation(action)
        results.append(r6)

        return results

    # -- Layer 1: Identity verification --

    async def _verify_identity(
        self, platform: str, platform_user_id: str
    ) -> ValidationResult:
        """Verify platform user is bound to a system user via Redis."""
        key = f"gateway:user_binding:{platform}:{platform_user_id}"
        bound_user_id = await self._redis.get(key)

        if not bound_user_id:
            logger.warning(
                "[Layer1:Identity] Unbound user: platform=%s, platform_user_id=%s",
                platform, platform_user_id,
            )
            return ValidationResult(
                passed=False,
                layer="identity",
                message=f"用户 {platform_user_id} 未绑定系统账号",
            )

        return ValidationResult(
            passed=True,
            layer="identity",
            detail={"bound_user_id": bound_user_id},
        )

    # -- Layer 2: Permission check --

    async def _check_permission(
        self, user_id: str, action_type: ActionType
    ) -> ValidationResult:
        """Verify user has permission for the action type."""
        if action_type in READONLY_ACTIONS:
            return ValidationResult(passed=True, layer="permission")

        # Check user permissions in Redis
        key = f"gateway:permissions:{user_id}"
        permissions = await self._redis.smembers(key)

        if not permissions:
            logger.warning(
                "[Layer2:Permission] No permissions found for user=%s", user_id
            )
            return ValidationResult(
                passed=False,
                layer="permission",
                message=f"用户 {user_id} 无操作权限",
            )

        if action_type.value not in permissions and "*" not in permissions:
            logger.warning(
                "[Layer2:Permission] User %s lacks permission for %s",
                user_id, action_type.value,
            )
            return ValidationResult(
                passed=False,
                layer="permission",
                message=f"用户无权限执行 {action_type.value} 操作",
            )

        return ValidationResult(passed=True, layer="permission")

    # -- Layer 3: Object validation --

    async def _validate_object(self, action: CallbackAction) -> ValidationResult:
        """Verify the target object exists and is in a valid state."""
        try:
            if action.target_type == TargetType.ROBOT:
                resp = await self._http_client.get(
                    f"{settings.CORE_PLATFORM_URL}/api/robot/{action.target_id}/status"
                )
                if resp.status_code == 404:
                    return ValidationResult(
                        passed=False, layer="object",
                        message=f"机器人 {action.target_id} 不存在",
                    )
                if resp.status_code != 200:
                    return ValidationResult(
                        passed=False, layer="object",
                        message=f"无法查询机器人状态: HTTP {resp.status_code}",
                    )
                robot_status = resp.json()
                # Check robot is in a state that allows this action
                if action.action_type == ActionType.ROBOT_STOP:
                    current_state = robot_status.get("state", "")
                    if current_state in ("IDLE", "CHARGING"):
                        return ValidationResult(
                            passed=False, layer="object",
                            message=f"机器人 {action.target_id} 当前状态 {current_state} 无需急停",
                        )

            elif action.target_type == TargetType.ORDER:
                resp = await self._http_client.get(
                    f"{settings.CORE_PLATFORM_URL}/api/order/{action.target_id}"
                )
                if resp.status_code == 404:
                    return ValidationResult(
                        passed=False, layer="object",
                        message=f"订单 {action.target_id} 不存在",
                    )
                if resp.status_code != 200:
                    return ValidationResult(
                        passed=False, layer="object",
                        message=f"无法查询订单状态: HTTP {resp.status_code}",
                    )
                order_data = resp.json()
                current_state = order_data.get("state", "")
                if action.action_type == ActionType.ORDER_CANCEL:
                    if current_state in ("COMPLETED", "CANCELLED", "SAP_CONFIRMED"):
                        return ValidationResult(
                            passed=False, layer="object",
                            message=f"订单 {action.target_id} 已处于终态 {current_state}，无法取消",
                        )

            elif action.target_type == TargetType.ZONE:
                resp = await self._http_client.get(
                    f"{settings.CORE_PLATFORM_URL}/api/zone/{action.target_id}/status"
                )
                if resp.status_code == 404:
                    return ValidationResult(
                        passed=False, layer="object",
                        message=f"区域 {action.target_id} 不存在",
                    )

        except httpx.RequestError as e:
            logger.error("[Layer3:Object] Request error: %s", e)
            return ValidationResult(
                passed=False, layer="object",
                message=f"对象校验请求失败: {e}",
            )

        return ValidationResult(passed=True, layer="object")

    # -- Layer 4: Anti-replay --

    async def _check_anti_replay(
        self,
        platform_user_id: str,
        action: CallbackAction,
        card_context: dict,
    ) -> ValidationResult:
        """Verify this exact operation hasn't been processed already."""
        # Build a unique fingerprint for this operation
        fingerprint_input = (
            f"{platform_user_id}:{action.action_type.value}:"
            f"{action.target_id}:{card_context.get('correlation_id', '')}"
        )
        fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()
        key = f"gateway:anti_replay:{fingerprint}"

        # Use SETNX (atomic) to check and set in one operation
        # TTL = confirm_timeout + 60s buffer
        ttl = settings.CONFIRM_TIMEOUT_SECONDS + 60
        inserted = await self._redis.set(key, "1", nx=True, ex=ttl)

        if not inserted:
            logger.warning(
                "[Layer4:AntiReplay] Duplicate operation detected: %s", fingerprint
            )
            return ValidationResult(
                passed=False, layer="anti_replay",
                message="重复操作，请勿重复点击",
            )

        return ValidationResult(passed=True, layer="anti_replay")

    # -- Layer 5: Secondary confirmation --

    async def _secondary_confirmation(
        self,
        action: CallbackAction,
        card_context: dict,
        confirm_token: Optional[str],
    ) -> ValidationResult:
        """For dangerous operations, require explicit secondary confirmation."""
        if action.action_type not in DANGEROUS_ACTIONS:
            return ValidationResult(passed=True, layer="secondary_confirm")

        # If no confirm_token provided, this is the first click
        # -> Generate a confirm_token and return (caller should send second card)
        if not confirm_token:
            import secrets
            token = secrets.token_urlsafe(32)
            alert_id = card_context.get("original_alert_id", "")
            key = f"gateway:confirm_token:{token}"
            token_data = {
                "action_type": action.action_type.value,
                "target_id": action.target_id,
                "alert_id": alert_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._redis.hset(key, mapping=token_data)
            await self._redis.expire(key, settings.CONFIRM_TIMEOUT_SECONDS)

            return ValidationResult(
                passed=False, layer="secondary_confirm",
                message="需要二次确认",
                detail={"confirm_token": token, "need_confirm": True},
            )

        # Verify the confirm_token
        key = f"gateway:confirm_token:{confirm_token}"
        token_data = await self._redis.hgetall(key)

        if not token_data:
            logger.warning("[Layer5:Confirm] Invalid or expired token: %s", confirm_token)
            return ValidationResult(
                passed=False, layer="secondary_confirm",
                message="确认令牌无效或已过期，请重新操作",
            )

        # Verify token matches the action
        if (
            token_data.get("action_type") != action.action_type.value
            or token_data.get("target_id") != action.target_id
        ):
            logger.warning("[Layer5:Confirm] Token-action mismatch")
            return ValidationResult(
                passed=False, layer="secondary_confirm",
                message="确认令牌与操作不匹配",
            )

        # Consume the token (delete it)
        await self._redis.delete(key)

        return ValidationResult(passed=True, layer="secondary_confirm")

    # -- Layer 6: Pre-execution validation --

    async def _pre_execution_validation(
        self, action: CallbackAction
    ) -> ValidationResult:
        """Verify the operation can be safely executed right now."""
        if action.action_type in READONLY_ACTIONS:
            return ValidationResult(passed=True, layer="pre_execution")

        # Check if system is in safe mode
        safe_mode = await self._redis.get("system:safe_mode")
        if safe_mode == "true" and action.action_type not in (
            ActionType.ROBOT_STOP,
            ActionType.ZONE_UNLOCK,
        ):
            return ValidationResult(
                passed=False, layer="pre_execution",
                message="系统处于安全模式，仅允许急停和解锁操作",
            )

        # Check emergency stop state for movement-related actions
        if action.action_type == ActionType.ROBOT_RECALL:
            estop_key = f"robot:{action.target_id}:estop"
            estop_state = await self._redis.get(estop_key)
            if estop_state == "true":
                return ValidationResult(
                    passed=False, layer="pre_execution",
                    message=f"机器人 {action.target_id} 处于急停状态，无法召回",
                )

        return ValidationResult(passed=True, layer="pre_execution")
