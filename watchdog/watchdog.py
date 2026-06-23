#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAP-EWM 机器人调度平台 - Watchdog 独立守护进程 v3.4 完整版
职责：多维度健康巡检、动态限流、致命熔断、安全模式、趋势告警
运行位置：独立容器，不依赖 Node-RED 事件循环
"""

import os
import sys
import time
import json
import signal
import logging
import hashlib
import base64
import hmac
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

import redis
import requests
import yaml

# ==========================================
# 配置加载（环境变量 > config.yaml > 默认值）
# ==========================================
CONFIG_PATH = os.getenv('WATCHDOG_CONFIG_PATH', '/app/config.yaml')

# 默认配置
DEFAULT_CONFIG = {
    'polling_interval': 10,
    'alert_cooldown': {
        'safe_mode': 60,
        'throttle': 300,
        'throttle_recovery': 300,
        'resource_warning': 600,
    },
    'thresholds': {
        'cpu_warning': 70,
        'cpu_critical': 80,
        'cpu_fatal': 95,
        'checkpoint_warning': 3000,
        'checkpoint_critical': 5000,
        'checkpoint_fatal': 10000,
        'memory_warning': 85,
        'memory_critical': 95,
        'wal_size_mb_warning': 50,
        'wal_size_mb_critical': 100,
        'redis_memory_ratio_warning': 0.8,
        'redis_memory_ratio_critical': 0.95,
        'nodered_unhealthy_count': 3,  # 连续几次不健康才判定
    },
    'throttle': {
        'min_rate': 10,
        'normal_rate_default': 50,
        'reduction_ratio': 0.3,
        'reduction_ratio_severe': 0.15,  # checkpoint 极高时
    },
    'recovery': {
        'consecutive_normal_required': 3,
        'cpu_recovery_ratio': 0.8,
        'checkpoint_recovery_ratio': 0.8,
        'memory_recovery_ratio': 0.85,
    },
    'safe_mode': {
        'redis_oom': True,
        'redis_evicted_keys_threshold': 100,
        'nodered_unhealthy': True,
        'nodered_cpu_fatal': False,
        'memory_oom': True,
        'checkpoint_stall': True,
    },
    'llm': {
        'daily_limit': 1000,
        'hourly_limit': 100,
        'block_duration': 3600,      # 超限后阻止调用时长（秒）
        'warning_threshold': 0.85,    # 达到 85% 预警
    },
    'feishu_templates': {
        'safe_mode': (
            "🔴 系统熔断保护\n"
            "原因：{reason}\n"
            "立即执行：\n"
            "1. `docker restart robot-platform-redis`\n"
            "2. `docker exec -it robot-platform-redis redis-cli --bigkeys`\n"
            "3. 访问急救页 http://{host}:8080\n"
            "如果不会操作，立刻拨打电话：{ops_phone}"
        ),
        'throttle': (
            "🟡 系统过载限流中\n"
            "当前指标：CPU {cpu:.1f}%，数据库写入延迟 {checkpoint}ms，内存 {memory:.1f}%\n"
            "已自动执行：限流至 {throttle_rate}单/秒，保障核心任务\n"
            "你需要做（选1）：\n"
            "1. 联系运维扩容服务器（2核→4核）\n"
            "2. 执行 `bash /app/scripts/cleanup_old_logs.sh` 清理旧日志\n"
            "3. 暂停非核心品牌机器人任务\n"
            "⏳ 30分钟未恢复，将自动进入安全模式！"
        ),
        'throttle_recovery': (
            "🟢 系统限流解除\n"
            "当前指标：CPU {cpu:.1f}%，Checkpoint {checkpoint}ms，内存 {memory:.1f}%\n"
            "系统已恢复正常派单速率。"
        ),
        'resource_warning': (
            "🟡 资源预警\n"
            "CPU: {cpu:.1f}%，内存: {memory:.1f}%，Checkpoint: {checkpoint}ms\n"
            "暂未达到限流阈值，但建议关注。"
        ),
        'llm_warning': (
            "🟡 LLM 调用预警\n"
            "当前用量：每日 {daily_count}/{daily_limit}，每小时 {hourly_count}/{hourly_limit}\n"
            "达到 {pct:.0f}% 限额，即将触发熔断。"
        ),
        'llm_blocked': (
            "🔴 LLM 调用熔断\n"
            "原因：{reason}\n"
            "已自动阻止 Dify 调用，降级至规则模板。\n"
            "如需恢复：`redis-cli DEL llm:blocked`"
        ),
    }
}

def load_config() -> Dict[str, Any]:
    """加载配置，环境变量覆盖文件配置"""
    config = DEFAULT_CONFIG.copy()

    # 尝试读取 config.yaml
    if Path(CONFIG_PATH).exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # 深度合并（简化版）
                    for key in ['thresholds', 'throttle', 'recovery', 'safe_mode', 'alert_cooldown']:
                        if key in file_config and isinstance(file_config[key], dict):
                            config[key].update(file_config[key])
                    for key in ['polling_interval', 'feishu_templates']:
                        if key in file_config:
                            config[key] = file_config[key]
        except Exception as e:
            logging.warning(f"读取 config.yaml 失败，使用默认配置: {e}")

    # 环境变量覆盖
    env_mappings = {
        'CPU_THRESHOLD': ('thresholds', 'cpu_critical', int),
        'CHECKPOINT_THRESHOLD': ('thresholds', 'checkpoint_critical', int),
        'THROTTLE_RATE_MIN': ('throttle', 'min_rate', int),
        'NORMAL_RATE_DEFAULT': ('throttle', 'normal_rate_default', int),
        'LLM_DAILY_LIMIT': ('llm', 'daily_limit', int),
        'LLM_HOURLY_LIMIT': ('llm', 'hourly_limit', int),
    }

    for env_key, (section, key, cast_type) in env_mappings.items():
        val = os.getenv(env_key)
        if val is not None:
            try:
                config[section][key] = cast_type(val)
            except ValueError:
                pass

    return config

CONFIG = load_config()

# ==========================================
# 环境变量（运行时）
# ==========================================
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
NODE_RED_CONTAINER = os.getenv('NODE_RED_CONTAINER', 'robot-platform-nodered')
SAP_BRIDGE_CONTAINER = os.getenv('SAP_BRIDGE_CONTAINER', 'robot-platform-sap-bridge')
MQTT_CONTAINER = os.getenv('MQTT_CONTAINER', 'robot-platform-mqtt')
FEISHU_WEBHOOK_URL = os.getenv('FEISHU_WEBHOOK_URL', '')
FEISHU_WEBHOOK_SECRET = os.getenv('FEISHU_WEBHOOK_SECRET', '')
# [Gap #12] 企微备用通道
WECOM_WEBHOOK_URL = os.getenv('WECOM_WEBHOOK_URL', '')
WECOM_CORP_ID = os.getenv('WECOM_CORP_ID', '')
WECOM_AGENT_ID = os.getenv('WECOM_AGENT_ID', '')
WECOM_SECRET = os.getenv('WECOM_SECRET', '')
OPS_PHONE = os.getenv('RESCUE_OPS_PHONE', '13800000000')
HOST = os.getenv('HOST', 'localhost')

# ==========================================
# 日志配置
# ==========================================
Path('/app/logs').mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/watchdog.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('watchdog')

# PID 文件
PID_FILE = '/app/.watchdog.pid'

# ==========================================
# 数据类：健康快照
# ==========================================
@dataclass
class HealthSnapshot:
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_limit_mb: float
    checkpoint_ms: int
    wal_size_mb: float
    redis_memory_used: int
    redis_memory_max: int
    redis_evicted_keys: int
    redis_connected_clients: int
    nodered_status: str  # healthy / unhealthy / unknown
    nodered_response_ms: int
    sap_bridge_status: str
    mqtt_status: str
    safe_mode: bool
    throttle_active: bool
    throttle_rate: int

    def to_dict(self) -> Dict:
        return asdict(self)

# ==========================================
# Redis 客户端（带重连和连接池）
# ==========================================
class RedisClient:
    def __init__(self, url: str):
        self.url = url
        self._client: Optional[redis.Redis] = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self):
        try:
            self._client = redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True
            )
            self._client.ping()
            logger.info("✅ Redis 连接成功")
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            self._client = None

    def _ensure_connected(self):
        if self._client is None:
            self._connect()
        try:
            self._client.ping()
        except redis.ConnectionError:
            logger.warning("Redis 连接断开，尝试重连...")
            self._connect()

    def get(self, key: str) -> Optional[str]:
        self._ensure_connected()
        if not self._client:
            return None
        try:
            return self._client.get(key)
        except redis.ConnectionError:
            self._connect()
            return None

    def set(self, key: str, value: str, ex: int = 0):
        self._ensure_connected()
        if not self._client:
            return
        try:
            if ex > 0:
                self._client.setex(key, ex, value)
            else:
                self._client.set(key, value)
        except redis.ConnectionError:
            self._connect()

    def delete(self, *keys: str):
        self._ensure_connected()
        if not self._client:
            return
        try:
            self._client.delete(*keys)
        except redis.ConnectionError:
            self._connect()

    def info(self, section: str = 'default') -> Dict[str, Any]:
        self._ensure_connected()
        if not self._client:
            return {}
        try:
            return self._client.info(section)
        except redis.ConnectionError:
            self._connect()
            return {}

    def incr(self, key: str) -> int:
        self._ensure_connected()
        if not self._client:
            return 0
        try:
            return self._client.incr(key)
        except redis.ConnectionError:
            self._connect()
            return 0

    def expire(self, key: str, ex: int):
        self._ensure_connected()
        if not self._client:
            return
        try:
            self._client.expire(key, ex)
        except redis.ConnectionError:
            self._connect()

    def lpush(self, key: str, value: str, max_len: int = 1000):
        """写入趋势队列，保留最近 N 条"""
        self._ensure_connected()
        if not self._client:
            return
        try:
            pipe = self._client.pipeline()
            pipe.lpush(key, value)
            pipe.ltrim(key, 0, max_len - 1)
            pipe.execute()
        except redis.ConnectionError:
            self._connect()

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        self._ensure_connected()
        if not self._client:
            return []
        try:
            return self._client.lrange(key, start, end)
        except redis.ConnectionError:
            self._connect()
            return []

redis_client = RedisClient(REDIS_URL)

# ==========================================
# 飞书告警（支持签名 + 模板变量替换）
# ==========================================
class FeishuAlerter:
    def __init__(self, webhook_url: str, secret: str = ''):
        self.webhook_url = webhook_url
        self.secret = secret
        self._last_alert_time: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_alert(self, key: str, cooldown_seconds: int) -> bool:
        with self._lock:
            now = time.time()
            last = self._last_alert_time.get(key, 0)
            if now - last >= cooldown_seconds:
                self._last_alert_time[key] = now
                return True
            return False

    def _gen_sign(self, timestamp: str) -> str:
        """飞书机器人签名（如果配置了 secret）"""
        if not self.secret:
            return ''
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode('utf-8')

    def send(self, title: str, content: str, level: str = "warning", template_key: str = '', **kwargs):
        """
        发送飞书告警
        :param title: 消息标题
        :param content: 正文内容（已格式化）
        :param level: info / warning / fatal
        :param template_key: 用于冷却控制的 key
        :param kwargs: 模板变量
        """
        if not self.webhook_url:
            logger.info(f"[飞书未配置] {title}: {content[:100]}...")
            return

        # 冷却检查
        if template_key:
            cooldown = CONFIG['alert_cooldown'].get(template_key, 300)
            if not self._should_alert(template_key, cooldown):
                logger.debug(f"[告警冷却] {title} 跳过发送")
                return

        # 模板变量替换
        template_vars = {
            'host': HOST,
            'ops_phone': OPS_PHONE,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }

        try:
            content = content.format(**template_vars)
        except KeyError as e:
            logger.warning(f"告警模板变量缺失: {e}")

        # 颜色映射
        color_map = {
            "info": "blue",
            "warning": "orange",
            "fatal": "red"
        }

        timestamp = str(int(time.time()))
        sign = self._gen_sign(timestamp)

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🚨 {title}"},
                    "template": color_map.get(level, "orange")
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                    {"tag": "hr"},
                    {"tag": "note", "elements": [
                        {"tag": "plain_text", "content": f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | 🔧 Watchdog v3.4 | 🐕 {NODE_RED_CONTAINER}"}
                    ]}
                ]
            }
        }

        # 如果有签名，加入
        if sign:
            payload['timestamp'] = timestamp
            payload['sign'] = sign

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            if resp.status_code != 200:
                logger.warning(f"飞书告警发送失败: HTTP {resp.status_code} {resp.text[:200]}")
            else:
                logger.info(f"✅ 飞书告警已发送: {title}")
        except Exception as e:
            logger.warning(f"飞书告警请求异常: {e}")

alerter = FeishuAlerter(FEISHU_WEBHOOK_URL, FEISHU_WEBHOOK_SECRET)

# ==========================================
# 企业微信告警（备用通道，Gap #12 修复）
# ==========================================
class WeComAlerter:
    """企微 Webhook 告警，飞书失败时自动切换"""
    def __init__(self, webhook_url: str = ''):
        self.webhook_url = webhook_url
        self._last_alert_time: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_alert(self, key: str, cooldown_seconds: int) -> bool:
        with self._lock:
            now = time.time()
            last = self._last_alert_time.get(key, 0)
            if now - last >= cooldown_seconds:
                self._last_alert_time[key] = now
                return True
            return False

    def send(self, title: str, content: str, level: str = "warning", template_key: str = ''):
        if not self.webhook_url:
            return
        if template_key:
            cooldown = CONFIG['alert_cooldown'].get(template_key, 300)
            if not self._should_alert(template_key, cooldown):
                return
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n{content}\n\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"企微告警发送失败: HTTP {resp.status_code}")
            else:
                logger.info(f"✅ 企微告警已发送: {title}")
        except Exception as e:
            logger.warning(f"企微告警请求异常: {e}")

wecom_alerter = WeComAlerter(WECOM_WEBHOOK_URL)

# ==========================================
# 指标采集器
# ==========================================
class MetricsCollector:
    """多维度指标采集：Docker stats + HTTP 探测 + Redis info + SQLite WAL"""

    @staticmethod
    def get_container_stats(container_name: str) -> Dict[str, Any]:
        """获取容器 CPU 和内存使用率"""
        result = {
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'memory_used_mb': 0.0,
            'memory_limit_mb': 0.0,
            'error': None
        }

        try:
            # docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}"
            proc = subprocess.run(
                [
                    'docker', 'stats', container_name,
                    '--no-stream', '--format',
                    '{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}'
                ],
                capture_output=True, text=True, timeout=15
            )

            if proc.returncode != 0:
                result['error'] = f"docker stats 失败: {proc.stderr.strip()}"
                return result

            parts = proc.stdout.strip().split('|')
            if len(parts) >= 3:
                # CPU: "45.23%"
                result['cpu_percent'] = float(parts[0].replace('%', '').strip())

                # Memory percent: "67.89%"
                result['memory_percent'] = float(parts[1].replace('%', '').strip())

                # Memory usage: "512MiB / 1GiB" or "1.5GiB / 2GiB"
                mem_usage = parts[2].strip()
                if ' / ' in mem_usage:
                    used_str, limit_str = mem_usage.split(' / ')
                    result['memory_used_mb'] = MetricsCollector._parse_memory(used_str)
                    result['memory_limit_mb'] = MetricsCollector._parse_memory(limit_str)

        except subprocess.TimeoutExpired:
            result['error'] = "docker stats 超时"
        except Exception as e:
            result['error'] = f"docker stats 异常: {e}"

        return result

    @staticmethod
    def _parse_memory(mem_str: str) -> float:
        """解析内存字符串为 MB"""
        mem_str = mem_str.strip().upper()

        # 去除可能的括号内容
        if '(' in mem_str:
            mem_str = mem_str.split('(')[0].strip()

        num_part = ''
        unit = 'MiB'

        for i, ch in enumerate(mem_str):
            if ch.isdigit() or ch == '.' :
                num_part += ch
            else:
                unit = mem_str[i:].strip()
                break

        try:
            num = float(num_part) if num_part else 0
        except ValueError:
            num = 0

        multipliers = {
            'B': 1 / (1024 * 1024),
            'KB': 1 / 1024,
            'KIB': 1 / 1024,
            'MB': 1,
            'MIB': 1,
            'GB': 1024,
            'GIB': 1024,
            'TB': 1024 * 1024,
            'TIB': 1024 * 1024,
        }

        return num * multipliers.get(unit, 1)

    @staticmethod
    def get_nodered_health() -> Dict[str, Any]:
        """HTTP 探测 Node-RED 健康端点"""
        result = {
            'status': 'unknown',
            'response_ms': 0,
            'checkpoint_ms': 0,
            'safe_mode': False,
            'throttle_mode': False,
            'error': None
        }

        try:
            start = time.time()
            resp = requests.get(
                f'http://{NODE_RED_CONTAINER}:1880/api/system-health',
                timeout=5
            )
            elapsed_ms = int((time.time() - start) * 1000)
            result['response_ms'] = elapsed_ms

            if resp.status_code == 200:
                result['status'] = 'healthy'
                data = resp.json()
                result['checkpoint_ms'] = data.get('checkpoint_ms', 0)
                result['safe_mode'] = data.get('safe_mode', False)
                result['throttle_mode'] = data.get('throttle_mode', False)
            else:
                result['status'] = 'unhealthy'
                result['error'] = f"HTTP {resp.status_code}"

        except requests.Timeout:
            result['status'] = 'unhealthy'
            result['error'] = 'HTTP 探测超时'
        except requests.ConnectionError:
            result['status'] = 'unhealthy'
            result['error'] = 'TCP 连接失败'
        except Exception as e:
            result['status'] = 'unknown'
            result['error'] = str(e)

        return result

    @staticmethod
    def get_redis_metrics() -> Dict[str, Any]:
        """获取 Redis 内存和连接指标"""
        result = {
            'memory_used': 0,
            'memory_max': 0,
            'memory_ratio': 0.0,
            'evicted_keys': 0,
            'connected_clients': 0,
            'error': None
        }

        try:
            info = redis_client.info('memory')
            if info:
                result['memory_used'] = info.get('used_memory', 0)
                result['memory_max'] = info.get('maxmemory', 0)
                if result['memory_max'] > 0:
                    result['memory_ratio'] = result['memory_used'] / result['memory_max']
                result['evicted_keys'] = info.get('evicted_keys', 0)

            clients_info = redis_client.info('clients')
            if clients_info:
                result['connected_clients'] = clients_info.get('connected_clients', 0)

        except Exception as e:
            result['error'] = f"Redis 指标采集失败: {e}"

        return result

    @staticmethod
    def check_clock_drift() -> Dict[str, Any]:
        """[Gap #11] NTP 时钟漂移检测：对比 Redis TIME 与本地时间"""
        result = {'drift_seconds': 0, 'status': 'ok', 'error': None}
        try:
            # Redis TIME 返回 [seconds, microseconds] (UTC)
            redis_time = redis_client._client.time() if redis_client._client else None
            if redis_time:
                redis_utc = datetime.fromtimestamp(redis_time[0] + redis_time[1] / 1_000_000, tz=timezone.utc)
                local_utc = datetime.now(timezone.utc)
                drift = abs((local_utc - redis_utc).total_seconds())
                result['drift_seconds'] = round(drift, 2)
                if drift > 30:
                    result['status'] = 'critical'
                elif drift > 5:
                    result['status'] = 'warning'
        except Exception as e:
            result['error'] = str(e)
        return result

    @staticmethod
    def get_sqlite_wal_size() -> float:
        """获取 SQLite WAL 文件大小（MB）"""
        try:
            # 尝试通过 Node-RED 容器内的文件系统读取
            wal_path = f"/var/lib/docker/volumes/robot-platform_nodered-data/_data/robot_platform.db-wal"

            # 先尝试直接读取（如果 Watchdog 与 Node-RED 共享卷）
            if Path(wal_path).exists():
                size_bytes = Path(wal_path).stat().st_size
                return size_bytes / (1024 * 1024)

            # 备选：通过 docker exec 在 Node-RED 容器内执行
            proc = subprocess.run(
                [
                    'docker', 'exec', NODE_RED_CONTAINER,
                    'ls', '-l', '/data/robot_platform.db-wal'
                ],
                capture_output=True, text=True, timeout=10
            )

            if proc.returncode == 0:
                parts = proc.stdout.strip().split()
                if len(parts) >= 5:
                    size_bytes = int(parts[4])
                    return size_bytes / (1024 * 1024)

            return 0.0

        except Exception as e:
            logger.warning(f"WAL 大小采集失败: {e}")
            return 0.0

    @staticmethod
    def get_container_health_status(container_name: str) -> str:
        """获取 Docker healthcheck 状态"""
        try:
            proc = subprocess.run(
                ['docker', 'inspect', '--format', '{{.State.Health.Status}}', container_name],
                capture_output=True, text=True, timeout=10
            )
            if proc.returncode == 0:
                return proc.stdout.strip() or 'unknown'
        except Exception:
            pass
        return 'unknown'

# ==========================================
# 决策引擎
# ==========================================
class WatchdogEngine:
    def __init__(self):
        self.safe_mode_active = False
        self.safe_mode_reason = ''
        self.throttle_active = False
        self.throttle_rate = 0
        self.normal_count = 0
        self.nodered_unhealthy_count = 0
        self.last_snapshot: Optional[HealthSnapshot] = None
        self._lock = threading.Lock()

        # 从 Redis 恢复状态（Watchdog 重启时）
        self._recover_state()

    def _recover_state(self):
        """从 Redis 恢复上次状态（防止 Watchdog 重启后状态丢失）"""
        try:
            sm = redis_client.get('system:safe_mode')
            if sm:
                self.safe_mode_active = True
                self.safe_mode_reason = sm
                logger.warning(f"🔄 从 Redis 恢复安全模式状态: {sm}")

            tr = redis_client.get('system:throttle_mode')
            if tr:
                self.throttle_active = True
                self.throttle_rate = int(tr)
                logger.warning(f"🔄 从 Redis 恢复限流状态: {tr} 单/秒")
        except Exception as e:
            logger.error(f"状态恢复失败: {e}")

    def _record_snapshot(self, snapshot: HealthSnapshot):
        """记录健康快照到 Redis（趋势分析）"""
        try:
            redis_client.lpush(
                'watchdog:health_snapshots',
                json.dumps(snapshot.to_dict()),
                max_len=2880  # 保留最近 2880 条（按 10 秒间隔 = 8 小时）
            )
        except Exception as e:
            logger.warning(f"快照记录失败: {e}")

    def enter_safe_mode(self, reason: str, snapshot: HealthSnapshot):
        """进入安全模式"""
        with self._lock:
            if self.safe_mode_active:
                return

            self.safe_mode_active = True
            self.safe_mode_reason = reason
            self.throttle_active = False
            self.throttle_rate = 0

            # 写入 Redis（Node-RED 读取后停止派单）
            redis_client.set('system:safe_mode', reason, ex=3600)
            redis_client.delete('system:throttle_mode')
            redis_client.set('system:safe_mode_triggered_at', datetime.now(timezone.utc).isoformat())

            logger.critical(f"🔴 致命熔断：进入安全模式，原因: {reason}")

            # 飞书告警
            template = CONFIG['feishu_templates'].get('safe_mode', '')
            alerter.send(
                title="系统熔断保护 - 安全模式已启动",
                content=template,
                level="fatal",
                template_key='safe_mode',
                reason=reason,
                cpu=snapshot.cpu_percent,
                checkpoint=snapshot.checkpoint_ms,
                memory=snapshot.memory_percent
            )
            # [Gap #12] 企微备用通道
            wecom_alerter.send("系统熔断保护",
                f"🔴 安全模式已启动\n原因: {reason}\nCPU: {snapshot.cpu_percent:.1f}%\nCheckpoint: {snapshot.checkpoint_ms}ms\n联系人: {OPS_PHONE}",
                level="fatal", template_key='safe_mode')

    def exit_safe_mode(self, reason: str = "manual"):
        """退出安全模式"""
        with self._lock:
            if not self.safe_mode_active:
                return

            self.safe_mode_active = False
            self.safe_mode_reason = ''

            redis_client.delete('system:safe_mode')
            redis_client.set('system:safe_mode_cleared_at', datetime.now(timezone.utc).isoformat())

            logger.info(f"🟢 安全模式已解除，原因: {reason}")

            alerter.send(
                title="系统恢复正常",
                content="安全模式已解除，系统恢复正常派单。",
                level="info",
                template_key='safe_mode_recovery'
            )
            wecom_alerter.send("系统恢复正常",
                "🟢 安全模式已解除，系统恢复正常派单。",
                level="info", template_key='safe_mode_recovery')

    def enter_throttle(self, rate: int, snapshot: HealthSnapshot, severity: str = "normal"):
        """进入限流模式"""
        with self._lock:
            if self.safe_mode_active:
                return

            self.throttle_active = True
            self.throttle_rate = rate
            self.normal_count = 0

            redis_client.set('system:throttle_mode', str(rate), ex=300)
            redis_client.set('system:throttle_severity', severity, ex=300)
            redis_client.set('system:last_throttle_alert', datetime.now(timezone.utc).isoformat())

            logger.warning(f"🟡 动态限流：限流至 {rate} 单/秒（严重度: {severity}）")

            template = CONFIG['feishu_templates'].get('throttle', '')
            alerter.send(
                title="系统过载限流中",
                content=template,
                level="warning",
                template_key='throttle',
                throttle_rate=rate,
                cpu=snapshot.cpu_percent,
                checkpoint=snapshot.checkpoint_ms,
                memory=snapshot.memory_percent,
                severity=severity
            )

    def exit_throttle(self, snapshot: HealthSnapshot):
        """解除限流"""
        with self._lock:
            if not self.throttle_active:
                return

            self.throttle_active = False
            self.throttle_rate = 0
            self.normal_count = 0

            redis_client.delete('system:throttle_mode')
            redis_client.delete('system:throttle_severity')
            redis_client.delete('system:normal_count')

            logger.info("🟢 限流解除：系统恢复正常")

            template = CONFIG['feishu_templates'].get('throttle_recovery', '')
            alerter.send(
                title="系统限流解除",
                content=template,
                level="info",
                template_key='throttle_recovery',
                cpu=snapshot.cpu_percent,
                checkpoint=snapshot.checkpoint_ms,
                memory=snapshot.memory_percent
            )

    def _calculate_throttle_rate(self, snapshot: HealthSnapshot) -> Tuple[int, str]:
        """计算限流速率，返回 (rate, severity)"""
        normal_rate = self._get_normal_rate()

        # 基础限流：降至 30%
        rate = max(CONFIG['throttle']['min_rate'], int(normal_rate * CONFIG['throttle']['reduction_ratio']))
        severity = "normal"

        # Checkpoint 极高，进一步降级
        if snapshot.checkpoint_ms > CONFIG['thresholds']['checkpoint_critical'] * 2:
            rate = max(CONFIG['throttle']['min_rate'], int(normal_rate * CONFIG['throttle']['reduction_ratio_severe']))
            severity = "severe"

        # 内存也告警，再降
        if snapshot.memory_percent > CONFIG['thresholds']['memory_critical']:
            rate = max(CONFIG['throttle']['min_rate'], int(rate * 0.5))
            severity = "critical"

        return rate, severity

    def _get_normal_rate(self) -> int:
        """获取历史正常峰值（Node-RED 运行时动态更新）"""
        val = redis_client.get('global:normal_rate')
        return int(val) if val else CONFIG['throttle']['normal_rate_default']

    def _is_normal(self, snapshot: HealthSnapshot) -> bool:
        """判断当前是否处于正常状态"""
        cpu_ok = snapshot.cpu_percent <= CONFIG['thresholds']['cpu_critical'] * CONFIG['recovery']['cpu_recovery_ratio']
        checkpoint_ok = snapshot.checkpoint_ms <= CONFIG['thresholds']['checkpoint_critical'] * CONFIG['recovery']['checkpoint_recovery_ratio']
        memory_ok = snapshot.memory_percent <= CONFIG['thresholds']['memory_critical'] * CONFIG['recovery']['memory_recovery_ratio']

        return cpu_ok and checkpoint_ok and memory_ok

    def _check_llm_cost(self):
        """LLM 调用成本熔断器：日限 1000 / 时 100，超限阻断"""
        today = datetime.now(timezone.utc).strftime('%Y%m%d')
        hour = datetime.now(timezone.utc).strftime('%Y%m%d%H')
        daily_limit = CONFIG['llm']['daily_limit']
        hourly_limit = CONFIG['llm']['hourly_limit']

        daily_count = redis_client.get(f'llm:daily_count:{today}')
        hourly_count = redis_client.get(f'llm:hourly_count:{hour}')
        daily_count = int(daily_count) if daily_count else 0
        hourly_count = int(hourly_count) if hourly_count else 0

        already_blocked = redis_client.get('llm:blocked')
        if already_blocked:
            logger.warning(f"LLM blocked: {already_blocked} (daily={daily_count}/{daily_limit})")
            return

        reason = None
        if daily_count >= daily_limit:
            reason = f'LLM_DAILY_LIMIT ({daily_count}/{daily_limit})'
        elif hourly_count >= hourly_limit:
            reason = f'LLM_HOURLY_LIMIT ({hourly_count}/{hourly_limit})'

        if reason:
            redis_client.set('llm:blocked', reason, ex=CONFIG['llm']['block_duration'])
            logger.critical(f"LLM cost fuse triggered: {reason}")
            alerter.send(
                title="LLM 调用熔断",
                content=CONFIG['feishu_templates'].get('llm_blocked', ''),
                level="fatal",
                template_key='llm_blocked',
                reason=reason,
            )
            return

        warning_pct = CONFIG['llm']['warning_threshold']
        daily_pct = daily_count / daily_limit if daily_limit > 0 else 0
        hourly_pct = hourly_count / hourly_limit if hourly_limit > 0 else 0

        if daily_pct >= warning_pct or hourly_pct >= warning_pct:
            if alerter._should_alert('llm_warning', CONFIG['alert_cooldown']['resource_warning']):
                pct = max(daily_pct, hourly_pct) * 100
                logger.warning(f"LLM approaching limit: {daily_count}/{daily_limit} daily, {hourly_count}/{hourly_limit} hourly")
                alerter.send(
                    title="LLM 调用预警",
                    content=CONFIG['feishu_templates'].get('llm_warning', ''),
                    level="warning",
                    template_key='llm_warning',
                    daily_count=daily_count, daily_limit=daily_limit,
                    hourly_count=hourly_count, hourly_limit=hourly_limit,
                    pct=pct,
                )

    def run_cycle(self):
        """单次巡检周期 - 完整决策逻辑"""
        # 1. 采集所有指标
        nodered_stats = MetricsCollector.get_container_stats(NODE_RED_CONTAINER)
        nodered_health = MetricsCollector.get_nodered_health()
        redis_metrics = MetricsCollector.get_redis_metrics()
        wal_size_mb = MetricsCollector.get_sqlite_wal_size()

        # 2. 构建快照
        snapshot = HealthSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            cpu_percent=nodered_stats.get('cpu_percent', 0),
            memory_percent=nodered_stats.get('memory_percent', 0),
            memory_used_mb=nodered_stats.get('memory_used_mb', 0),
            memory_limit_mb=nodered_stats.get('memory_limit_mb', 0),
            checkpoint_ms=nodered_health.get('checkpoint_ms', 0),
            wal_size_mb=wal_size_mb,
            redis_memory_used=redis_metrics.get('memory_used', 0),
            redis_memory_max=redis_metrics.get('memory_max', 0),
            redis_evicted_keys=redis_metrics.get('evicted_keys', 0),
            redis_connected_clients=redis_metrics.get('connected_clients', 0),
            nodered_status=nodered_health.get('status', 'unknown'),
            nodered_response_ms=nodered_health.get('response_ms', 0),
            sap_bridge_status=MetricsCollector.get_container_health_status(SAP_BRIDGE_CONTAINER),
            mqtt_status=MetricsCollector.get_container_health_status(MQTT_CONTAINER),
            safe_mode=self.safe_mode_active,
            throttle_active=self.throttle_active,
            throttle_rate=self.throttle_rate
        )

        self.last_snapshot = snapshot
        self._record_snapshot(snapshot)

        # [Gap #11] NTP 时钟漂移检测
        clock_drift = MetricsCollector.check_clock_drift()
        if clock_drift['status'] == 'critical' and not self.safe_mode_active:
            logger.critical(f"🔴 NTP 时钟漂移严重: {clock_drift['drift_seconds']}s")
            self.enter_safe_mode(f'CLOCK_DRIFT_{clock_drift["drift_seconds"]}s', snapshot)
            alerter.send(
                title="NTP 时钟漂移严重",
                content=f"🔴 时钟偏差 {clock_drift['drift_seconds']}s，已触发安全模式。",
                level="fatal",
                template_key='safe_mode'
            )
            wecom_alerter.send("NTP 时钟漂移严重",
                f"🔴 时钟偏差 {clock_drift['drift_seconds']}s，已触发安全模式。")
            return
        elif clock_drift['status'] == 'warning':
            logger.warning(f"🟡 NTP 时钟漂移警告: {clock_drift['drift_seconds']}s")

        # 3. 日志输出（结构化）
        logger.info(
            f"📊 巡检: CPU={snapshot.cpu_percent:.1f}% Mem={snapshot.memory_percent:.1f}% "
            f"Checkpoint={snapshot.checkpoint_ms}ms WAL={snapshot.wal_size_mb:.1f}MB "
            f"RedisMemRatio={redis_metrics.get('memory_ratio', 0):.1%} "
            f"NodeRED={snapshot.nodered_status}({snapshot.nodered_response_ms}ms) "
            f"SafeMode={snapshot.safe_mode} Throttle={snapshot.throttle_active}({snapshot.throttle_rate})"
        )

        # 4. 致命熔断检查（优先级最高）

        # 4.1 Redis OOM
        if CONFIG['safe_mode']['redis_oom'] and redis_metrics.get('memory_ratio', 0) > CONFIG['thresholds']['redis_memory_ratio_critical']:
            self.enter_safe_mode('REDIS_OOM', snapshot)
            return

        # 4.2 Redis 大量驱逐
        if CONFIG['safe_mode']['redis_evicted_keys_threshold'] and redis_metrics.get('evicted_keys', 0) > CONFIG['thresholds'].get('redis_evicted_keys_threshold', 100):
            self.enter_safe_mode('REDIS_EVICTION_SPIKE', snapshot)
            return

        # 4.3 Node-RED 不健康（连续多次）
        if snapshot.nodered_status != 'healthy':
            self.nodered_unhealthy_count += 1
            if CONFIG['safe_mode']['nodered_unhealthy'] and self.nodered_unhealthy_count >= CONFIG['thresholds']['nodered_unhealthy_count']:
                self.enter_safe_mode(f'NODERED_UNHEALTHY_{snapshot.nodered_status}', snapshot)
                return
        else:
            self.nodered_unhealthy_count = 0

        # 4.4 Node-RED 内存 OOM
        if CONFIG['safe_mode']['memory_oom'] and snapshot.memory_percent > 99:
            self.enter_safe_mode('NODERED_MEMORY_OOM', snapshot)
            return

        # 4.5 Checkpoint 完全卡死
        if CONFIG['safe_mode']['checkpoint_stall'] and snapshot.checkpoint_ms > CONFIG['thresholds']['checkpoint_fatal']:
            self.enter_safe_mode('CHECKPOINT_STALL', snapshot)
            return

        # 5. 动态限流检查（仅在非安全模式下）
        cpu_critical = snapshot.cpu_percent > CONFIG['thresholds']['cpu_critical']
        checkpoint_critical = snapshot.checkpoint_ms > CONFIG['thresholds']['checkpoint_critical']
        memory_critical = snapshot.memory_percent > CONFIG['thresholds']['memory_critical']
        wal_critical = snapshot.wal_size_mb > CONFIG['thresholds']['wal_size_mb_critical']

        # 限流触发条件：CPU 和 Checkpoint 双高，或内存极高，或 WAL 过大
        should_throttle = (cpu_critical and checkpoint_critical) or memory_critical or wal_critical

        if should_throttle:
            rate, severity = self._calculate_throttle_rate(snapshot)

            # 如果已经在限流，且严重度上升，更新限流值
            if self.throttle_active:
                current_severity = redis_client.get('system:throttle_severity') or 'normal'
                if severity != current_severity or rate != self.throttle_rate:
                    self.enter_throttle(rate, snapshot, severity)
            else:
                self.enter_throttle(rate, snapshot, severity)
            return

        # 6. 资源预警（仅日志和低频告警，不限流）
        cpu_warning = snapshot.cpu_percent > CONFIG['thresholds']['cpu_warning']
        checkpoint_warning = snapshot.checkpoint_ms > CONFIG['thresholds']['checkpoint_warning']
        memory_warning = snapshot.memory_percent > CONFIG['thresholds']['memory_warning']
        wal_warning = snapshot.wal_size_mb > CONFIG['thresholds']['wal_size_mb_warning']

        if cpu_warning or checkpoint_warning or memory_warning or wal_warning:
            if alerter._should_alert('resource_warning', CONFIG['alert_cooldown']['resource_warning']):
                template = CONFIG['feishu_templates'].get('resource_warning', '')
                alerter.send(
                    title="资源预警",
                    content=template,
                    level="warning",
                    template_key='resource_warning',
                    cpu=snapshot.cpu_percent,
                    checkpoint=snapshot.checkpoint_ms,
                    memory=snapshot.memory_percent,
                    wal=snapshot.wal_size_mb
                )

        # [LLM] 成本熔断检查（日限 1000 / 时 100）
        self._check_llm_cost()

        # 7. 恢复检测（连续多次正常才解除限流，防抖动）
        if self.throttle_active:
            if self._is_normal(snapshot):
                self.normal_count += 1
                redis_client.incr('system:normal_count')
                redis_client.expire('system:normal_count', 300)

                logger.info(f"🟡 恢复计数: {self.normal_count}/{CONFIG['recovery']['consecutive_normal_required']}")

                if self.normal_count >= CONFIG['recovery']['consecutive_normal_required']:
                    self.exit_throttle(snapshot)
            else:
                # 未恢复，重置计数
                self.normal_count = 0
                redis_client.delete('system:normal_count')

# ==========================================
# HTTP API（供外部查询 Watchdog 状态）
# ==========================================
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class WatchdogHTTPHandler(BaseHTTPRequestHandler):
    """极简 HTTP 接口，供 Prometheus / 运维脚本采集"""

    def log_message(self, format, *args):
        # 静默日志，避免污染
        pass

    def do_GET(self):
        if self.path == '/health':
            self._send_json({'status': 'ok', 'pid': os.getpid()})
        elif self.path == '/metrics':
            engine = self.server.engine
            snapshot = engine.last_snapshot
            if snapshot:
                self._send_json({
                    'watchdog_version': 'v3.4',
                    'safe_mode': engine.safe_mode_active,
                    'safe_mode_reason': engine.safe_mode_reason,
                    'throttle_active': engine.throttle_active,
                    'throttle_rate': engine.throttle_rate,
                    'snapshot': snapshot.to_dict()
                })
            else:
                self._send_json({'error': 'no snapshot yet'}, 503)
        elif self.path == '/snapshots':
            # 返回最近 10 条趋势
            try:
                data = redis_client.lrange('watchdog:health_snapshots', 0, 9)
                snapshots = [json.loads(d) for d in data]
                self._send_json({'snapshots': snapshots})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
        else:
            self._send_json({'error': 'not found'}, 404)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

def start_http_server(engine: WatchdogEngine, port=9090):
    """启动 HTTP 服务线程"""
    server = HTTPServer(('0.0.0.0', port), WatchdogHTTPHandler)
    server.engine = engine
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"🌐 Watchdog HTTP API 已启动: http://0.0.0.0:{port}")
    return server

# ==========================================
# 信号处理（优雅退出）
# ==========================================
def signal_handler(signum, frame):
    logger.info(f"收到信号 {signum}，正在优雅退出...")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ==========================================
# 主循环
# ==========================================
def main():
    logger.info("=" * 70)
    logger.info("🐕 SAP-EWM Watchdog v3.4 完整版启动")
    logger.info(f"   目标容器: {NODE_RED_CONTAINER}")
    logger.info(f"   CPU 阈值: {CONFIG['thresholds']['cpu_critical']}%")
    logger.info(f"   Checkpoint 阈值: {CONFIG['thresholds']['checkpoint_critical']}ms")
    logger.info(f"   内存阈值: {CONFIG['thresholds']['memory_critical']}%")
    logger.info(f"   限流下限: {CONFIG['throttle']['min_rate']} 单/秒")
    logger.info(f"   飞书告警: {'已配置' if FEISHU_WEBHOOK_URL else '未配置'}")
    logger.info(f"   LLM 日限: {CONFIG['llm']['daily_limit']} 次, 时限: {CONFIG['llm']['hourly_limit']} 次")
    logger.info("=" * 70)

    # 写入 PID 文件
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    # 初始化引擎
    engine = WatchdogEngine()

    # 启动 HTTP API（供 Prometheus / 运维采集）
    http_port = int(os.getenv('WATCHDOG_HTTP_PORT', '9090'))
    start_http_server(engine, http_port)

    # 主巡检循环
    interval = CONFIG['polling_interval']

    while True:
        cycle_start = time.time()

        try:
            engine.run_cycle()
        except Exception as e:
            logger.exception(f"巡检周期异常: {e}")
            # 异常不退出，继续下一个周期

        # 精确控制间隔（扣除执行时间）
        elapsed = time.time() - cycle_start
        sleep_time = max(0, interval - elapsed)

        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            logger.warning(f"巡检周期执行耗时 {elapsed:.1f}s，超过间隔 {interval}s，建议扩容")

if __name__ == '__main__':
    main()
