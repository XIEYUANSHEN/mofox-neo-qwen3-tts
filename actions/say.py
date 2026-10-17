"""say_voice —— 把一段文字用配置的音色合成语音并发出去。"""

from __future__ import annotations

import asyncio
import base64
import re
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_text, send_voice
from src.app.plugin_system.base import BaseAction
from src.app.plugin_system.types import ChatType

from ..config import Qwen3TTSConfig
from ..tts_client import synthesize

logger = get_logger("qwen3_tts.say")

# 会被 TTS 念出来的 markdown / 结构符号
_MD_CHARS = re.compile(r"[*_`#>\[\](){}~|\\]")
# emoji 与杂项符号
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U0000FE00-\U0000FE0F\U00002B00-\U00002BFF\u200d]"
)
_PUNCT = "，。！？；、,.!?;"


def _clean_text(text: str) -> str:
    """清掉 TTS 不该念的东西：markdown、emoji、换行、重复标点。"""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\n+", "，", t)          # 换行 → 逗号（别断句断得太硬）
    t = _MD_CHARS.sub("", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[ \t\u3000]+", " ", t)
    t = re.sub(r"([，。！？；、])\1+", r"\1", t)   # 连续标点只留一个
    t = re.sub(r"^[，。！？；、\s]+", "", t)       # 开头不留标点
    return t.strip()


def _smart_truncate(text: str, limit: int) -> str:
    """超长时优先在标点处断开，避免截在词中间。"""
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(p) for p in _PUNCT)
    if cut >= int(limit * 0.6):
        return head[: cut + 1]
    return head


def _to_mp3(wav_path: Path, ffmpeg: str) -> tuple[bool, bytes, str]:
    """用 ffmpeg 把 wav 转 mp3，返回 (成功, 字节, 说明)。"""
    mp3_path = wav_path.with_suffix(".mp3")
    try:
        proc = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-qscale:a", "4", str(mp3_path)],
            capture_output=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        return False, b"", f"ffmpeg 执行失败: {e}"
    if proc.returncode != 0 or not mp3_path.is_file():
        err = (proc.stderr or b"").decode("utf-8", "ignore")[:200]
        return False, b"", f"ffmpeg 返回 {proc.returncode}: {err}"
    try:
        return True, mp3_path.read_bytes(), str(mp3_path)
    except Exception as e:  # noqa: BLE001
        return False, b"", f"读 mp3 失败: {e}"


class SayVoiceAction(BaseAction):
    """用配置的音色发语音消息。"""

    name = "say_voice"
    description = (
        "【调用名是 action-say_voice，照抄；不要写成 tool-say_voice】\n"
        "用配置的音色说一句话，以语音消息发给对方。\n"
        "什么时候用：对方明确想听你的声音/要语音时，或这句话用声音说出来更合适。\n"
        "注意：合成一次要十几秒，比较费资源，别频繁调用；"
        "一次只放一句话（不要超过 120 字），不要塞长段落或列表。\n"
        "参数 content：要说的纯文本，不要带引号、不要加括号说明。"
    )

    chat_type = ChatType.PRIVATE
    associated_platforms: list[str] = ["qq"]
    associated_types = ["text"]
    chatter_allow: list[str] = []
    primary_action = False

    _last_at: float = 0.0

    def _cfg(self) -> Qwen3TTSConfig | None:
        cfg = self.plugin.config
        return cfg if isinstance(cfg, Qwen3TTSConfig) else None

    def _is_private(self) -> bool:
        raw = str(getattr(self.chat_stream, "chat_type", "") or "").strip().lower()
        return "private" in raw

    async def go_activate(self) -> bool:
        cfg = self._cfg()
        if not (cfg and cfg.plugin.enabled):
            return False
        if not self._is_private() and not cfg.plugin.allow_group:
            return False
        return True

    async def execute(
        self,
        content: Annotated[str, "要合成语音的文本（一句话，<=120字）"] = "",
        **extra: Any,
    ) -> tuple[bool, str]:
        # ---- 1. 取文本（参数名容错）----
        if not content:
            for k in ("text", "message", "msg", "voice_text", "arg", "value", "words"):
                v = extra.get(k)
                if isinstance(v, str) and v.strip():
                    content = v
                    logger.info(f"content 由别名 {k} 命中")
                    break
        content = _clean_text(str(content or "").strip().strip('"').strip("'"))
        if not content:
            return False, "没拿到可用的文本（content 为空或清洗后为空）"

        cfg = self._cfg()
        if cfg is None:
            return False, "插件配置未加载"

        # ---- 2. 门控：群聊 ----
        if not self._is_private() and not cfg.plugin.allow_group:
            return False, "当前是群聊，未开启群聊语音（配置 allow_group=true 可开）"

        # ---- 3. 长度 ----
        if len(content) < cfg.plugin.min_chars:
            return False, f"文本太短（少于 {cfg.plugin.min_chars} 字），没必要发语音"
        raw_len = len(content)
        content = _smart_truncate(content, cfg.plugin.max_chars)
        if len(content) < raw_len:
            logger.info(f"文本 {raw_len} 字超过上限，按标点截断到 {len(content)} 字")

        # ---- 4. 冷却 ----
        now = time.time()
        cd = max(0, int(cfg.plugin.cooldown_s))
        gap = now - SayVoiceAction._last_at
        if cd and gap < cd:
            return False, f"刚发过语音，请等 {int(cd - gap) + 1} 秒再说"

        # ---- 5. 合成 ----
        out_dir = Path(cfg.plugin.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"v_{int(now * 1000)}.wav"

        t0 = time.time()
        ok, msg, wav = await asyncio.to_thread(
            synthesize,
            endpoint=cfg.tts.endpoint,
            token=cfg.tts.token,
            text=content,
            ref_wav=cfg.voice.ref_wav,
            ref_text=cfg.voice.ref_text,
            language=cfg.voice.language,
            out_path=str(out_path),
            timeout=int(cfg.tts.timeout),
        )
        if not ok:
            logger.warning(f"TTS 合成失败 | text={content[:30]!r} | {msg}")
            return False, f"语音合成失败：{msg}"

        # ---- 6. 可选转码 ----
        audio_bytes, suffix = wav, "wav"
        if cfg.send.transcode_mp3:
            mp3_ok, mp3_bytes, info = await asyncio.to_thread(
                _to_mp3, out_path, cfg.send.ffmpeg_path)
            if mp3_ok:
                audio_bytes, suffix = mp3_bytes, "mp3"
            else:
                logger.warning(f"转 mp3 失败，仍用 wav 发送 | {info}")

        SayVoiceAction._last_at = time.time()
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        # ---- 7. 发送 ----
        stream_id = str(getattr(self.chat_stream, "stream_id", "") or "")
        platform = str(getattr(self.chat_stream, "platform", "") or "") or None
        if not stream_id:
            logger.error("拿不到 stream_id，放弃发送")
            return False, "拿不到 chat_stream.stream_id，无法发送"

        sent, send_err = False, ""
        try:
            sent = bool(await send_voice(
                audio_b64, stream_id, platform=platform,
                processed_plain_text="[语音]"))
        except Exception as e:  # noqa: BLE001
            send_err = f"{type(e).__name__}: {e}"
            logger.exception("send_voice 抛异常")

        cost = time.time() - t0

        # ---- 8. 清理（成功才删；失败按配置保留）----
        keep = cfg.plugin.keep_files or (not sent and cfg.plugin.keep_on_fail)
        if not keep:
            try:
                out_path.unlink(missing_ok=True)
                out_path.with_suffix(".mp3").unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
        else:
            logger.info(f"保留音频文件: {out_path}")

        if not sent:
            reason = send_err or "send_voice 返回 False"
            logger.warning(
                f"语音发送失败 | {len(content)}字 | {cost:.1f}s | {suffix} | "
                f"{len(audio_bytes)}B | {reason} | 文件={out_path}")
            # 可选兜底：补发文字
            if cfg.send.fallback_text:
                try:
                    await send_text(f"{cfg.send.fallback_text}{content}",
                                    stream_id, platform=platform)
                except Exception:  # noqa: BLE001
                    logger.exception("补发文字也失败了")
            return False, (f"语音发送失败（{reason}）。"
                           f"可以改用文字回复；音频已留存在 {out_path}")

        logger.info(
            f"语音已发出 | {len(content)}字 | {cost:.1f}s | {suffix} | {len(audio_bytes)}B")
        return True, f"已发出语音（{cost:.1f}秒）"
