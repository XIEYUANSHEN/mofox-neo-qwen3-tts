"""qwen3_tts 插件配置。"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class Qwen3TTSConfig(BaseConfig):
    """Qwen3-TTS 语音插件配置。"""

    name: ClassVar[str] = "config"
    description: ClassVar[str] = "qwen3_tts 配置"

    @config_section("plugin")
    class PluginSection(SectionBase):
        """插件行为配置。"""

        enabled: bool = Field(default=True, description="是否启用 qwen3_tts")

        allow_group: bool = Field(
            default=False, description="是否允许在群聊里发语音（默认只私聊）")

        max_chars: int = Field(
            default=120, description="单次合成允许的最大字数（超出按标点截断）")

        min_chars: int = Field(
            default=2, description="低于此长度的文本不合成（避免浪费算力）")

        cooldown_s: int = Field(
            default=8, description="两次语音之间的最小间隔（秒），防连刷")

        out_dir: str = Field(
            default="/tmp/qwen3_tts", description="音频临时输出目录")

        keep_files: bool = Field(
            default=False, description="是否保留生成的音频文件（默认发完即删）")

        keep_on_fail: bool = Field(
            default=True, description="失败时是否保留音频文件（便于排查）")

    @config_section("tts")
    class TTSSection(SectionBase):
        """TTS 服务连接配置。"""

        endpoint: str = Field(
            default="http://127.0.0.1:8897/synthesize",
            description="Qwen3-TTS sidecar 合成接口")

        token: str = Field(
            default="",
            description="接口鉴权 token（X-TTS-Token）；留空表示不鉴权")

        timeout: int = Field(default=180, description="合成请求超时（秒）")

    @config_section("voice")
    class VoiceSection(SectionBase):
        """音色配置（留空则用服务端默认音色）。"""

        ref_wav: str = Field(
            default="", description="参考音频绝对路径；留空=服务默认音色")

        ref_text: str = Field(
            default="", description="参考音频对应文本；留空=服务默认")

        language: str = Field(default="Chinese", description="合成语言")

    @config_section("send")
    class SendSection(SectionBase):
        """发送行为配置。"""

        transcode_mp3: bool = Field(
            default=False,
            description="发送前用 ffmpeg 转成 mp3（若 NapCat 不收 wav 就打开）")

        ffmpeg_path: str = Field(default="ffmpeg", description="ffmpeg 路径")

        fallback_text: str = Field(
            default="", description="语音失败时补发的文字；留空=不补发")

    # ⚠️ 必须显式声明字段！Pydantic 不会自动挂载 @config_section 的嵌套类，
    #    缺了这几行 cfg.plugin 就会 AttributeError（框架报"加载失败"）。
    plugin: PluginSection = Field(default_factory=PluginSection)
    tts: TTSSection = Field(default_factory=TTSSection)
    voice: VoiceSection = Field(default_factory=VoiceSection)
    send: SendSection = Field(default_factory=SendSection)