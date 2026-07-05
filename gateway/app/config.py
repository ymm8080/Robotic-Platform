"""Gateway configuration - all settings loaded from environment variables."""
import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    # General
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8010"))
    TZ: str = os.getenv("TZ", "UTC")

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    KAFKA_ALERT_TOPIC: str = os.getenv("KAFKA_ALERT_TOPIC", "platform_alerts")
    KAFKA_CALLBACK_TOPIC: str = os.getenv("KAFKA_CALLBACK_TOPIC", "gateway_callbacks")
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "message-gateway")

    # Elasticsearch
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_PASSWORD: str = os.getenv("ELASTICSEARCH_PASSWORD", "robot-platform-es")
    ELASTICSEARCH_INDEX_PREFIX: str = os.getenv("ELASTICSEARCH_INDEX_PREFIX", "gateway_audit")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/2")

    # WeChat (企业微信)
    WECOM_CORP_ID: str = os.getenv("WECOM_CORP_ID", "")
    WECOM_AGENT_ID: str = os.getenv("WECOM_AGENT_ID", "")
    WECOM_SECRET: str = os.getenv("WECOM_SECRET", "")
    WECOM_TOKEN: str = os.getenv("WECOM_TOKEN", "")
    WECOM_ENCODING_AES_KEY: str = os.getenv("WECOM_ENCODING_AES_KEY", "")

    # Feishu (飞书)
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")

    # DingTalk (钉钉)
    DINGTALK_APP_KEY: str = os.getenv("DINGTALK_APP_KEY", "")
    DINGTALK_APP_SECRET: str = os.getenv("DINGTALK_APP_SECRET", "")
    DINGTALK_ROBOT_CODE: str = os.getenv("DINGTALK_ROBOT_CODE", "")
    DINGTALK_SIGN_SECRET: str = os.getenv("DINGTALK_SIGN_SECRET", "")

    # SMTP
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD_FILE: str = os.getenv("SMTP_PASSWORD_FILE", "/run/secrets/smtp_password")
    SMTP_FROM_ADDR: str = os.getenv("SMTP_FROM_ADDR", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # Core Platform
    CORE_PLATFORM_URL: str = os.getenv("CORE_PLATFORM_URL", "http://nodered:1880")

    # Validation
    CONFIRM_TIMEOUT_SECONDS: int = int(os.getenv("CONFIRM_TIMEOUT_SECONDS", "300"))
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "1095"))

    @property
    def smtp_password(self) -> str:
        """Read SMTP password from Docker Secret file."""
        try:
            return Path(self.SMTP_PASSWORD_FILE).read_text().strip()
        except (FileNotFoundError, PermissionError):
            return ""

    @property
    def enabled_channels(self) -> list[str]:
        """Return list of enabled notification channels based on config."""
        channels = []
        if self.WECOM_CORP_ID:
            channels.append("wechat")
        if self.FEISHU_APP_ID:
            channels.append("feishu")
        if self.DINGTALK_APP_KEY:
            channels.append("dingtalk")
        if self.SMTP_HOST:
            channels.append("email")
        return channels


settings = Settings()
