"""qwen3_tts 的 TTS 客户端 —— 调本机 Qwen3-TTS sidecar。

这是纯同步实现（urllib），调用方需用 asyncio.to_thread 包起来，
避免阻塞 bot 的事件循环。
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def synthesize(
    *,
    endpoint: str,
    token: str,
    text: str,
    ref_wav: str = "",
    ref_text: str = "",
    language: str = "Chinese",
    out_path: str = "",
    timeout: int = 180,
) -> tuple[bool, str, bytes]:
    """调用 TTS 服务合成语音。

    Returns:
        (是否成功, 说明/错误信息, wav 字节)。失败时 bytes 为空。
    """
    body: dict[str, object] = {"text": text}
    if ref_wav:
        body["ref_wav"] = ref_wav
    if ref_text:
        body["ref_text"] = ref_text
    if language:
        body["language"] = language
    if out_path:
        body["output"] = out_path

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(endpoint, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-TTS-Token", token)

    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}", b""
    except URLError as e:
        return False, f"连不上 TTS 服务: {e.reason}", b""
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}", b""

    if not isinstance(result, dict) or not result.get("ok"):
        err = (result or {}).get("error") if isinstance(result, dict) else "响应格式异常"
        return False, str(err or "合成失败"), b""

    path = Path(str(result.get("path") or ""))
    if not path.is_file():
        return False, f"服务返回的音频文件不存在: {path}", b""

    try:
        return True, str(path), path.read_bytes()
    except Exception as e:  # noqa: BLE001
        return False, f"读取音频失败: {e}", b""
