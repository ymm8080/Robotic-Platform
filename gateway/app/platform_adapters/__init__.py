"""Platform adapters package."""
from .wechat import WeChatAdapter
from .feishu import FeishuAdapter
from .dingtalk import DingTalkAdapter

__all__ = ["WeChatAdapter", "FeishuAdapter", "DingTalkAdapter"]
