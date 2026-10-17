"""qwen3_tts —— 让 bot 用本地 Qwen3-TTS 服务把文字合成语音消息发出去。

音色由配置里的参考音频（ref_wav / ref_text / language）决定，不绑定某个固定角色；
本插件只负责：拿文本 -> 调 TTS 服务合成 -> 用 send_api.send_voice 发出去。
"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin

from .actions.say import SayVoiceAction
from .config import Qwen3TTSConfig

logger = get_logger("qwen3_tts")


@register_plugin
class Qwen3TTSPlugin(BasePlugin):
    """Qwen3-TTS 语音插件。"""

    plugin_name = "qwen3_tts"
    plugin_description = "把文字交给 Qwen3-TTS 服务合成语音消息发出去"
    plugin_version = "1.0.0"

    configs: list[type] = [Qwen3TTSConfig]
    dependent_components: list[str] = []

    def get_components(self) -> list[type]:
        cfg = self.config
        if isinstance(cfg, Qwen3TTSConfig) and not cfg.plugin.enabled:
            logger.info("qwen3_tts 已在配置中禁用")
            return []
        endpoint = cfg.tts.endpoint if isinstance(cfg, Qwen3TTSConfig) else "?"
        logger.info(f"qwen3_tts 已启用，TTS 服务: {endpoint}")
        return [SayVoiceAction]