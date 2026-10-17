#!/usr/bin/env python3
"""qwen3_tts 插件逻辑测试（注入假框架模块，验证 execute 各分支）

覆盖：
  1. 文本清洗（markdown / emoji / 换行）
  2. 智能截断（标点优先）
  3. 正常流程（mock 合成 + mock 发送）
  4. 群聊拒绝
  5. 文本太短
  6. TTS 合成失败
  7. 发送失败 -> 文件应保留
  8. 参数名容错（LLM 传 text 而非 content）

说明：合成与发送均被 mock，测试不依赖本地 TTS 服务，也不携带任何真实 token。
"""
import asyncio
import logging
import sys
import types
from pathlib import Path

# 插件所在目录的父目录（仓库根）加入 path，使 `qwen3_tts` 成为顶层包
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 以脚本直接运行时补上包上下文，使相对导入可用
if __package__ in (None, ""):
    __package__ = "qwen3_tts.tests"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SENT: list[tuple] = []          # 记录 send_voice / send_text 调用
SEND_RESULT: list[bool] = [True]   # 可变，用来切换成功/失败

FAKE_WAV = b"RIFF" + b"\x00" * 64   # 假 wav 字节


def _mk(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# ---------- 假框架 ----------
for pkg in ("src", "src.app", "src.app.plugin_system",
            "src.app.plugin_system.api", "src.app.plugin_system.types"):
    _mk(pkg)

_mk("src.app.plugin_system.api.log_api", get_logger=logging.getLogger)


async def _fake_send_voice(data, stream_id, **kw):
    SENT.append(("voice", stream_id, kw.get("platform"), len(data)))
    return SEND_RESULT[0]


async def _fake_send_text(text, stream_id, **kw):
    SENT.append(("text", stream_id, kw.get("platform"), text))
    return True


_mk("src.app.plugin_system.api.send_api",
    send_voice=_fake_send_voice, send_text=_fake_send_text)


class _ChatType:
    ALL = "all"
    PRIVATE = "private"
    GROUP = "group"


_mk("src.app.plugin_system.types", ChatType=_ChatType)


class _SectionBase:
    pass


class _BaseConfig:
    """够用的假实现：把 @config_section("x") 的嵌套类实例成 x 属性。"""
    def __init__(self, **override):
        for attr in dir(type(self)):
            sub = getattr(type(self), attr)
            if isinstance(sub, type) and issubclass(sub, _SectionBase) and sub is not _SectionBase:
                inst = sub()
                for k in getattr(sub, "__annotations__", {}):
                    if not hasattr(inst, k):
                        setattr(inst, k, None)
                setattr(self, getattr(sub, "__section_name__", attr), inst)
        for k, v in override.items():
            setattr(self, k, v)


def _field(default=None, **kw):
    return default


def _config_section(name):
    def deco(cls):
        cls.__section_name__ = name
        return cls
    return deco


def _register_plugin(cls):
    return cls


class _BaseAction:
    plugin = None
    chat_stream = None


_mk("src.app.plugin_system.base",
    BaseConfig=_BaseConfig, SectionBase=_SectionBase, Field=_field,
    config_section=_config_section, BaseAction=_BaseAction,
    register_plugin=_register_plugin, BasePlugin=object)


# ---------- 载入被测插件 ----------
from ..actions import say as say_mod  # type: ignore
from ..actions.say import SayVoiceAction, _clean_text, _smart_truncate  # type: ignore
from ..config import Qwen3TTSConfig  # type: ignore


def _fake_synthesize_ok(endpoint, token, text, ref_wav, ref_text,
                        language, out_path, timeout):
    Path(out_path).write_bytes(FAKE_WAV)
    return True, "ok", FAKE_WAV


def _fake_synthesize_fail(endpoint, token, text, ref_wav, ref_text,
                          language, out_path, timeout):
    return False, "mock 合成失败", b""


class FakeStream:
    def __init__(self, chat_type="private", sid="qq_user_1", platform="qq"):
        self.chat_type = chat_type
        self.stream_id = sid
        self.platform = platform


def make_action(cfg: Qwen3TTSConfig, chat_type="private"):
    a = SayVoiceAction()
    a.plugin = types.SimpleNamespace(config=cfg)
    a.chat_stream = FakeStream(chat_type=chat_type)
    return a


def base_cfg(**plugin_kw):
    cfg = Qwen3TTSConfig()
    cfg.tts.endpoint = "http://127.0.0.1:8897/synthesize"
    cfg.tts.token = ""                    # 测试用空 token，不依赖真实鉴权
    cfg.tts.timeout = 150
    cfg.plugin.cooldown_s = 0             # 测试时关冷却
    cfg.plugin.keep_on_fail = True
    cfg.plugin.out_dir = "/tmp/qwen3_tts_test"
    for k, v in plugin_kw.items():
        setattr(cfg.plugin, k, v)
    return cfg


async def main():
    print("=" * 60)
    print("[1] 文本清洗")
    dirty = "**你好**，我是#某某#呀😊\n\n人家在这里哦~~~ [链接](http://x)"
    cleaned = _clean_text(dirty)
    print("  原始:", repr(dirty))
    print("  清洗:", repr(cleaned))
    assert "*" not in cleaned and "#" not in cleaned and "😊" not in cleaned
    assert "\n" not in cleaned
    print("  -> PASS")

    print("[2] 智能截断（标点优先）")
    long_text = "第一句话，第二句话。第三句话；第四句话！" * 12
    cut = _smart_truncate(long_text, 30)
    print(f"  原长 {len(long_text)} -> {len(cut)} | 结尾: {cut[-6:]!r}")
    assert len(cut) <= 30 and cut[-1] in "，。！？；、"
    print("  -> PASS")

    print("[3] 正常流程（mock 合成 + mock 发送）")
    SENT.clear(); SEND_RESULT[0] = True
    say_mod.synthesize = _fake_synthesize_ok
    cfg = base_cfg()
    a = make_action(cfg)
    ok, msg = await a.execute(content="测试一下，说句话。")
    print(f"  ok={ok} msg={msg}")
    print(f"  SENT={SENT}")
    assert ok and SENT and SENT[0][0] == "voice"
    print("  -> PASS")

    print("[4] 群聊应被拒绝")
    SENT.clear()
    a = make_action(base_cfg(), chat_type="group")
    ok, msg = await a.execute(content="群里也要说话")
    print(f"  ok={ok} msg={msg}")
    assert not ok and not SENT
    print("  -> PASS")

    print("[5] 文本太短应被拒绝")
    a = make_action(base_cfg())
    ok, msg = await a.execute(content="。")
    print(f"  ok={ok} msg={msg}")
    assert not ok
    print("  -> PASS")

    print("[6] TTS 合成失败")
    say_mod.synthesize = _fake_synthesize_fail
    cfg = base_cfg()
    a = make_action(cfg)
    ok, msg = await a.execute(content="这条应该失败")
    print(f"  ok={ok} msg={msg}")
    assert not ok
    print("  -> PASS")

    print("[7] 发送失败 -> 应保留音频文件")
    SENT.clear(); SEND_RESULT[0] = False
    say_mod.synthesize = _fake_synthesize_ok
    cfg = base_cfg()
    cfg.plugin.out_dir = "/tmp/qwen3_tts_test_keep"
    a = make_action(cfg)
    ok, msg = await a.execute(content="发送会失败的这条")
    print(f"  ok={ok} msg={msg}")
    files = list(Path(cfg.plugin.out_dir).glob("*.wav"))
    print(f"  留存文件: {[f.name for f in files]}")
    assert not ok and files, "失败时应保留文件便于排查"
    print("  -> PASS")

    print("[8] 参数名容错（LLM 传 text 而非 content）")
    SENT.clear(); SEND_RESULT[0] = True
    a = make_action(base_cfg())
    ok, msg = await a.execute(text="用别名传进来的话")
    print(f"  ok={ok} msg={msg}")
    assert ok and SENT
    print("  -> PASS")

    print("=" * 60)
    print("ALL_TESTS_PASSED")


if __name__ == "__main__":
    asyncio.run(main())