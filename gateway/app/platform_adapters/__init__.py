"""Platform adapters package."""

from .dingtalk import DingTalkAdapter
from .feishu import FeishuAdapter
from .wechat import WeChatAdapter

__all__ = ["WeChatAdapter", "FeishuAdapter", "DingTalkAdapter"]
